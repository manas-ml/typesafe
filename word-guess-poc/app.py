#!/usr/bin/env python3
"""
Tiny Flask server that demonstrates the Jev-in-a-loop word guesser live in a
browser: each request to /api/play runs one full game (see solver.py) and
returns the complete round-by-round transcript, which the page then
animates one round at a time.

Run:
    python app.py
    open http://localhost:5000
"""

import random

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from data.words import ANSWER_WORDS
from solver import play_game

load_dotenv()

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/play", methods=["POST"])
def api_play():
    body = request.get_json(silent=True) or {}
    baseline = bool(body.get("baseline", False))
    secret = random.choice(ANSWER_WORDS)
    try:
        result = play_game(secret, baseline=baseline)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(result)


if __name__ == "__main__":
    # Avoid 5000: on macOS it's claimed by the AirPlay Receiver (ControlCenter),
    # which answers with a 403 that browsers render as "Access Denied".
    app.run(debug=True, port=5050)
