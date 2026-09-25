"""
The guessing-game loop: a human thinks of something from data/entities.py and
answers yes/no/unsure to questions; the loop narrows a belief distribution
over candidates and eventually commits to a guess.

What stays in code (exact): the belief-update math (Bayesian-style weight
multiply + renormalize) using the precomputed data/matrix.json, and the
information-gain ranking used to shortlist candidate questions. Jev supplies
two genuinely fuzzy per-round judgments that the precomputed matrix cannot
answer on its own:

  1. Which question (among the top information-gain candidates) is actually
     the best one to ask next, given how the game has gone so far.
  2. Whether the current belief is confident enough to commit to a guess yet,
     and if so, which of the leading candidates is the right one.

Both are confidence-gated: a low-confidence Jev answer falls back to the
plain code-computed choice (highest information gain / highest belief)
rather than acting on a shaky judgment.
"""

import json
import math
import os

from data.entities import ENTITIES
from data.questions import QUESTIONS
from jev_client import call_jev

MATRIX_PATH = os.path.join(os.path.dirname(__file__), "data", "matrix.json")

MAX_ROUNDS = 15
MAX_GUESS_ATTEMPTS = 3
QUESTION_SHORTLIST_SIZE = 5
GUESS_SHORTLIST_SIZE = 5
QUESTION_CONFIDENCE_THRESHOLD = 0.3
GUESS_CONFIDENCE_THRESHOLD = 0.3
GUESS_NOUL_THRESHOLD = 0.55
MIN_UPDATE_FACTOR = 0.02  # floor so one bad matrix answer can't zero an entity out forever

ENTITY_BY_ID = {e["id"]: e for e in ENTITIES}
QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}

if not os.path.exists(MATRIX_PATH):
    raise RuntimeError(
        f"{MATRIX_PATH} not found. Run `python generate_matrix.py` first "
        "to precompute the entity/question answer matrix."
    )
with open(MATRIX_PATH) as f:
    MATRIX = json.load(f)


def _binary_entropy(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def new_weights() -> dict:
    n = len(ENTITIES)
    return {e["id"]: 1.0 / n for e in ENTITIES}


def top_candidates(weights: dict, n: int) -> list:
    return sorted(weights.items(), key=lambda kv: -kv[1])[:n]


def _question_info_gain(question_id: str, weights: dict) -> float:
    p_yes = sum(w * MATRIX[eid][question_id] for eid, w in weights.items())
    return _binary_entropy(p_yes)


def pick_question(weights: dict, asked_ids: list) -> tuple:
    """Return (question_id, round_info)."""
    remaining = [q for q in QUESTIONS if q["id"] not in asked_ids]
    ranked = sorted(remaining, key=lambda q: -_question_info_gain(q["id"], weights))
    shortlist = ranked[:QUESTION_SHORTLIST_SIZE]

    if len(shortlist) == 1:
        qid = shortlist[0]["id"]
        return qid, {"used_fallback": True, "fallback_reason": "only one question left", "jev_choice": None, "jev_confidence": None, "shortlist": [q["id"] for q in shortlist]}

    leaders = top_candidates(weights, 5)
    state = {
        "leading_candidates": [
            {"name": ENTITY_BY_ID[eid]["name"], "probability": round(w, 3)} for eid, w in leaders
        ],
        "candidate_questions": [
            {"id": q["id"], "text": q["template"].format(name="it")}
            for q in shortlist
        ],
    }
    questions = {
        "next_question": {
            "type": "choice",
            "instructions": (
                "You're playing a 20-questions-style guessing game, trying to "
                "identify what a person is thinking of by asking yes/no "
                "questions. Each candidate question below was chosen because "
                "it splits your current belief about the leading candidates "
                "well. Given the current leading candidates and how the game "
                "has gone so far, which of these questions is the best one to "
                "ask next?"
            ),
            "criteria": {q["id"]: q["template"].format(name="it") for q in shortlist},
        }
    }
    answers = call_jev(state, questions)
    choice = answers["next_question"]
    picked = choice.get("choice")
    confidence = choice.get("confidence", 0.0)

    valid_ids = {q["id"] for q in shortlist}
    used_fallback = picked not in valid_ids or confidence < QUESTION_CONFIDENCE_THRESHOLD
    qid = ranked[0]["id"] if used_fallback else picked

    return qid, {
        "used_fallback": used_fallback,
        "fallback_reason": None if not used_fallback else "low Jev confidence",
        "jev_choice": picked,
        "jev_confidence": confidence,
        "shortlist": [q["id"] for q in shortlist],
    }


def update_weights(weights: dict, question_id: str, answer: str) -> dict:
    updated = {}
    for eid, w in weights.items():
        p_yes = MATRIX[eid][question_id]
        if answer == "yes":
            factor = max(p_yes, MIN_UPDATE_FACTOR)
        elif answer == "no":
            factor = max(1 - p_yes, MIN_UPDATE_FACTOR)
        else:  # "unsure" -- no information, leave unchanged
            factor = 1.0
        updated[eid] = w * factor

    total = sum(updated.values()) or 1.0
    return {eid: w / total for eid, w in updated.items()}


def should_guess(weights: dict, round_num: int) -> tuple:
    """Return (decision: bool, round_info)."""
    if round_num >= MAX_ROUNDS:
        return True, {"used_fallback": True, "fallback_reason": "max rounds reached", "jev_confidence": None}

    leaders = top_candidates(weights, 5)
    state = {
        "round": round_num,
        "leading_candidates": [
            {"name": ENTITY_BY_ID[eid]["name"], "probability": round(w, 3)} for eid, w in leaders
        ],
    }
    questions = {
        "confident_enough": {
            "type": "noul",
            "instructions": (
                "In this 20-questions-style guessing game, given the current "
                "probability distribution over remaining candidates, are you "
                "confident enough to commit to a final guess right now, rather "
                "than asking another clarifying question?"
            ),
            "criteria": {"true": "Confident enough to guess now.", "false": "Should ask another question first."},
        }
    }
    answers = call_jev(state, questions)
    p = answers["confident_enough"].get("noul", 0.0)
    return p >= GUESS_NOUL_THRESHOLD, {"used_fallback": False, "fallback_reason": None, "jev_confidence": p}


def final_guess(weights: dict) -> tuple:
    """Return (entity_id, round_info)."""
    shortlist = top_candidates(weights, GUESS_SHORTLIST_SIZE)

    if len(shortlist) == 1:
        eid = shortlist[0][0]
        return eid, {"used_fallback": True, "fallback_reason": "only one candidate left", "jev_choice": None, "jev_confidence": None}

    state = {
        "leading_candidates": [
            {"id": eid, "name": ENTITY_BY_ID[eid]["name"], "probability": round(w, 3)} for eid, w in shortlist
        ],
    }
    questions = {
        "final_guess": {
            "type": "choice",
            "instructions": (
                "Based on all the yes/no answers so far, which of these "
                "leading candidates is most likely the actual thing the "
                "person is thinking of?"
            ),
            "criteria": {eid: ENTITY_BY_ID[eid]["name"] for eid, _ in shortlist},
        }
    }
    answers = call_jev(state, questions)
    choice = answers["final_guess"]
    picked = choice.get("choice")
    confidence = choice.get("confidence", 0.0)

    valid_ids = {eid for eid, _ in shortlist}
    used_fallback = picked not in valid_ids or confidence < GUESS_CONFIDENCE_THRESHOLD
    guess_id = shortlist[0][0] if used_fallback else picked

    return guess_id, {
        "used_fallback": used_fallback,
        "fallback_reason": None if not used_fallback else "low Jev confidence",
        "jev_choice": picked,
        "jev_confidence": confidence,
    }
