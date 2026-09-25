#!/usr/bin/env python3
"""
Flask server for the 20-questions-style guessing game: you think of something
from data/entities.py, Jev asks yes/no questions and tries to guess it.

Game state lives server-side in an in-memory dict keyed by a game_id (fine
for a single-process demo; not meant to survive a restart or scale out).

Run:
    python app.py
    open http://localhost:5051
"""

import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from data.questions import QUESTIONS
from game import (
    ENTITY_BY_ID,
    MAX_GUESS_ATTEMPTS,
    MAX_ROUNDS,
    QUESTION_BY_ID,
    final_guess,
    new_weights,
    pick_question,
    should_guess,
    update_weights,
)

load_dotenv()

app = Flask(__name__)
GAMES = {}


def question_text(question_id: str) -> str:
    return QUESTION_BY_ID[question_id]["template"].format(name="it")


def _new_question_response(state: dict) -> dict:
    qid, info = pick_question(state["weights"], state["asked"])
    state["asked"].append(qid)
    state["round"] += 1
    state["pending_question_id"] = qid
    return {
        "type": "question",
        "round": state["round"],
        "max_rounds": MAX_ROUNDS,
        "question_id": qid,
        "question_text": question_text(qid),
        "question_info": info,
    }


def _guess_or_question_response(state: dict) -> dict:
    decide, guess_check_info = should_guess(state["weights"], state["round"])
    if not decide:
        response = _new_question_response(state)
        response["guess_check_info"] = guess_check_info
        return response

    eid, guess_info = final_guess(state["weights"])
    state["pending_guess_id"] = eid
    return {
        "type": "guess",
        "round": state["round"],
        "guess_attempt": state["guess_attempts"] + 1,
        "max_guess_attempts": MAX_GUESS_ATTEMPTS,
        "entity_name": ENTITY_BY_ID[eid]["name"],
        "guess_check_info": guess_check_info,
        "guess_info": guess_info,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    game_id = str(uuid.uuid4())
    state = {
        "weights": new_weights(),
        "asked": [],
        "round": 0,
        "guess_attempts": 0,
        "pending_question_id": None,
        "pending_guess_id": None,
    }
    GAMES[game_id] = state

    try:
        response = _new_question_response(state)
    except Exception as exc:
        del GAMES[game_id]
        return jsonify({"error": str(exc)}), 502

    response["game_id"] = game_id
    return jsonify(response)


@app.route("/api/answer", methods=["POST"])
def api_answer():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    answer = body.get("answer")
    state = GAMES.get(game_id)
    if not state or answer not in ("yes", "no", "unsure"):
        return jsonify({"error": "invalid game_id or answer"}), 400

    qid = state["pending_question_id"]
    state["weights"] = update_weights(state["weights"], qid, answer)
    state["pending_question_id"] = None

    try:
        response = _guess_or_question_response(state)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    response["game_id"] = game_id
    return jsonify(response)


@app.route("/api/guess_feedback", methods=["POST"])
def api_guess_feedback():
    body = request.get_json(silent=True) or {}
    game_id = body.get("game_id")
    correct = bool(body.get("correct"))
    state = GAMES.get(game_id)
    if not state:
        return jsonify({"error": "invalid game_id"}), 400

    eid = state.pop("pending_guess_id", None)

    if correct:
        response = {
            "type": "end",
            "result": "win",
            "entity_name": ENTITY_BY_ID[eid]["name"] if eid else None,
            "round": state["round"],
            "guess_attempts": state["guess_attempts"] + 1,
        }
        del GAMES[game_id]
        return jsonify(response)

    state["guess_attempts"] += 1
    if eid:
        state["weights"][eid] = 0.0
        total = sum(state["weights"].values()) or 1.0
        state["weights"] = {k: v / total for k, v in state["weights"].items()}

    exhausted = (
        state["guess_attempts"] >= MAX_GUESS_ATTEMPTS
        or state["round"] >= MAX_ROUNDS
        or len(state["asked"]) >= len(QUESTIONS)
    )
    if exhausted:
        response = {
            "type": "end",
            "result": "lose",
            "round": state["round"],
            "guess_attempts": state["guess_attempts"],
        }
        del GAMES[game_id]
        return jsonify(response)

    try:
        response = _guess_or_question_response(state)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    response["game_id"] = game_id
    return jsonify(response)


if __name__ == "__main__":
    # Avoid 5000 (macOS AirPlay Receiver) and 5050 (used by word-guess-poc)
    # so both POCs' web UIs can run at the same time without a port clash.
    app.run(debug=True, port=5051)
