#!/usr/bin/env python3
"""
A code-owned loop that plays a Wordle-style word-guessing game to
completion, calling Jev once per round for the one genuinely fuzzy
decision: among several candidate guesses that all maximize expected
information gain, which one is most likely to actually be the answer.

Everything else -- feedback scoring, candidate filtering, entropy
computation, the loop itself, and win/loss detection -- is exact and stays
in code (see wordle.py). If Jev's confidence in its pick is too low, the
loop falls back to the plain top-entropy candidate instead of guessing
blind on a bad model call.

Usage:
    python solver.py                        # play 1 game, print the report
    python solver.py --games 50             # aggregate stats over 50 games
    python solver.py --games 50 --baseline  # same, but skip Jev entirely
    python solver.py --games 10 --verbose   # print every round's transcript
"""

import argparse
import statistics
import sys

from dotenv import load_dotenv

from data.words import ANSWER_WORDS
from jev_client import call_jev
from wordle import entropy, filter_candidates, score_guess

load_dotenv()

MAX_GUESSES = 6
SHORTLIST_SIZE = 8
CONFIDENCE_THRESHOLD = 0.35


def build_choice_question(shortlist: list) -> dict:
    criteria = {word: f'the word "{word}"' for word, _ in shortlist}
    return {
        "next_guess": {
            "type": "choice",
            "instructions": (
                "You are choosing the next guess in a Wordle-style word-guessing "
                "game. Each candidate below was selected because it maximizes "
                "expected information gain against the remaining possible answer "
                "words. Among these information-maximizing candidates, which one "
                "is most likely to actually be today's secret answer word, based "
                "on how common and familiar it is as an everyday word (rather "
                "than an obscure or rarely-used one)?"
            ),
            "criteria": criteria,
        }
    }


def pick_guess(candidates: list, round_num: int) -> tuple:
    """Return (guess, round_info). round_info records what Jev was shown and
    whether the confidence-gated fallback kicked in, for the transcript."""
    scored = sorted(
        ((c, entropy(c, candidates)) for c in candidates), key=lambda x: -x[1]
    )
    shortlist = scored[:SHORTLIST_SIZE]

    if len(shortlist) == 1:
        word, _ = shortlist[0]
        return word, {
            "used_fallback": True,
            "fallback_reason": "only one candidate left",
            "jev_choice": None,
            "jev_confidence": None,
            "shortlist": shortlist,
        }

    state = {
        "round": round_num,
        "candidates_remaining": len(candidates),
        "shortlisted_guesses": [
            {"word": w, "expected_information_bits": round(e, 3)} for w, e in shortlist
        ],
    }
    answers = call_jev(state, build_choice_question(shortlist))
    choice = answers["next_guess"]
    picked = choice.get("choice")
    confidence = choice.get("confidence", 0.0)

    valid_words = {w for w, _ in shortlist}
    used_fallback = picked not in valid_words or confidence < CONFIDENCE_THRESHOLD
    guess = shortlist[0][0] if used_fallback else picked

    return guess, {
        "used_fallback": used_fallback,
        "fallback_reason": None if not used_fallback else "low Jev confidence",
        "jev_choice": picked,
        "jev_confidence": confidence,
        "shortlist": shortlist,
    }


def play_game(secret: str, max_guesses: int = MAX_GUESSES, baseline: bool = False) -> dict:
    """Play one game to completion (win or exhausted guesses) and return a
    structured transcript."""
    candidates = list(ANSWER_WORDS)
    transcript = []

    for round_num in range(1, max_guesses + 1):
        if baseline:
            guess = max(candidates, key=lambda c: entropy(c, candidates))
            round_info = {
                "used_fallback": True,
                "fallback_reason": "baseline mode (Jev not consulted)",
                "jev_choice": None,
                "jev_confidence": None,
                "shortlist": None,
            }
        else:
            guess, round_info = pick_guess(candidates, round_num)

        feedback = score_guess(guess, secret)
        candidates = filter_candidates(candidates, guess, feedback)

        transcript.append(
            {
                "round": round_num,
                "guess": guess,
                "feedback": feedback,
                "candidates_remaining": len(candidates),
                **round_info,
            }
        )

        if feedback == "GGGGG":
            return {"won": True, "guesses": round_num, "secret": secret, "transcript": transcript}

    return {"won": False, "guesses": max_guesses, "secret": secret, "transcript": transcript}


def print_transcript(result: dict) -> None:
    outcome = "WON" if result["won"] else "LOST"
    print(f"  secret={result['secret']}  {outcome} in {result['guesses']} guess(es)")
    for r in result["transcript"]:
        note = f"jev={r['jev_choice']!r} conf={r['jev_confidence']}"
        if r["used_fallback"]:
            note += f"  [fallback: {r['fallback_reason']}]"
        print(
            f"    round {r['round']}: guess={r['guess']}  feedback={r['feedback']}  "
            f"remaining={r['candidates_remaining']:4d}  {note}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--baseline", action="store_true", help="skip Jev, always take top-entropy guess")
    parser.add_argument("--verbose", action="store_true", help="print every game's round-by-round transcript")
    args = parser.parse_args()

    import random

    rng = random.Random(args.seed)
    n = min(args.games, len(ANSWER_WORDS))
    secrets = rng.sample(ANSWER_WORDS, n)

    print(f"Playing {n} game(s){' (baseline, no Jev)' if args.baseline else ''}...")
    results = []
    for i, secret in enumerate(secrets, start=1):
        try:
            result = play_game(secret, baseline=args.baseline)
        except Exception as exc:
            print(f"  game {i} ({secret}) failed: {exc}")
            continue
        results.append(result)
        if args.verbose:
            print_transcript(result)
        elif i % 10 == 0 or i == n:
            print(f"  {i}/{n} games done")

    if not results:
        print("No games completed.")
        sys.exit(1)

    wins = [r for r in results if r["won"]]
    win_guesses = [r["guesses"] for r in wins]
    histogram = {k: 0 for k in range(1, MAX_GUESSES + 1)}
    for r in results:
        if r["won"]:
            histogram[r["guesses"]] += 1

    print(f"\n=== Report ({len(results)} games) ===")
    print(f"Win rate: {len(wins)}/{len(results)} ({len(wins) / len(results):.0%})")
    if win_guesses:
        print(f"Guesses on wins: mean={statistics.mean(win_guesses):.2f}  median={statistics.median(win_guesses):.1f}")
    print("Guess-count histogram (wins only):")
    for k in range(1, MAX_GUESSES + 1):
        print(f"  {k}: {'#' * histogram[k]} ({histogram[k]})")
    losses = len(results) - len(wins)
    if losses:
        print(f"Failed to solve within {MAX_GUESSES} guesses: {losses}")


if __name__ == "__main__":
    main()
