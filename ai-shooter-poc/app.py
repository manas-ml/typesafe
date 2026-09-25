#!/usr/bin/env python3
"""
A lightweight top-down shooter where enemy tactical decisions are made by
Jev, live -- but only periodically (roughly every ~2 seconds per enemy), not
every frame. This is a different loop shape than word-guess-poc or
twenty-questions-poc: there, the loop paused waiting for a human turn; here,
code owns a real-time physics/render loop running at 60fps in the browser,
and calls this endpoint every so often to refresh one enemy's *intent*
(advance/retreat/strafe/hold/flee) plus an aggression level that scales its
speed and fire rate. Between calls, the enemy keeps executing its last
decision -- exactly the "code owns the loop, Jev supplies one bounded
judgment per round" pattern, just on a game-loop cadence instead of a
turn-based one.

Run:
    python app.py
    open http://localhost:5052
"""

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from jev_client import call_jev

load_dotenv()

app = Flask(__name__)

ACTIONS = {
    "advance": "Move directly toward the player to close the distance and attack.",
    "retreat": "Move away from the player to a safer distance while continuing to fight.",
    "strafe": "Move sideways relative to the player, staying roughly at the same distance, to be a harder target while attacking.",
    "hold_and_fire": "Stay in place and focus on attacking as accurately as possible.",
    "flee": "Disengage and run directly away from the player, prioritizing survival over attacking.",
}

AGGRESSION_LEVELS = [
    "Passive: minimal engagement, prioritizes safety heavily.",
    "Cautious: engages carefully, willing to disengage if things go badly.",
    "Aggressive: pushes the fight, willing to take some risk to land hits.",
    "Reckless: all-out attack, largely ignoring its own safety.",
]

CONFIDENCE_THRESHOLD = 0.3


def fallback_action(enemy_health_frac: float, distance: float, near_range: float, far_range: float) -> str:
    if enemy_health_frac < 0.3:
        return "flee"
    if distance > far_range:
        return "advance"
    if distance < near_range:
        return "retreat"
    return "hold_and_fire"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/enemy_decision", methods=["POST"])
def enemy_decision():
    body = request.get_json(silent=True) or {}
    try:
        enemy_health_frac = float(body["enemy_health_fraction"])
        player_health_frac = float(body["player_health_fraction"])
        distance = float(body["distance"])
        near_range = float(body.get("near_range", 130))
        far_range = float(body.get("far_range", 320))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "invalid payload"}), 400

    state = {
        "enemy_health_fraction": round(enemy_health_frac, 2),
        "player_health_fraction": round(player_health_frac, 2),
        "distance_to_player": round(distance, 1),
        "near_range_threshold": near_range,
        "far_range_threshold": far_range,
    }
    questions = {
        "next_action": {
            "type": "choice",
            "instructions": (
                "You control one enemy combatant in a top-down shooter game. "
                "Given your own health, the player's apparent health, and your "
                "distance to the player (relative to the near/far thresholds "
                "given), choose the best tactical action to take for the next "
                "couple of seconds."
            ),
            "criteria": ACTIONS,
        },
        "aggression": {
            "type": "score",
            "instructions": (
                "How aggressively should you play this encounter right now, "
                "given the same situation? This scales your movement speed "
                "and fire rate for the next couple of seconds."
            ),
            "criteria": AGGRESSION_LEVELS,
        },
    }

    try:
        answers = call_jev(state, questions)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    action_answer = answers["next_action"]
    picked = action_answer.get("choice")
    confidence = action_answer.get("confidence", 0.0)
    used_fallback = picked not in ACTIONS or confidence < CONFIDENCE_THRESHOLD
    action = (
        fallback_action(enemy_health_frac, distance, near_range, far_range)
        if used_fallback
        else picked
    )

    aggression_answer = answers.get("aggression", {})

    return jsonify(
        {
            "action": action,
            "aggression_score": aggression_answer.get("score", 1.5),
            "aggression_confidence": aggression_answer.get("confidence"),
            "jev_choice": picked,
            "jev_confidence": confidence,
            "used_fallback": used_fallback,
            "fallback_reason": None if not used_fallback else "low Jev confidence",
        }
    )


if __name__ == "__main__":
    # 5000 is claimed by macOS AirPlay Receiver; 5050/5051 are used by the
    # other two loop POCs in this repo.
    app.run(debug=True, port=5052)
