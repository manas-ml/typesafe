#!/usr/bin/env python3
"""
Precompute an entity x question truth-probability matrix: for every entity in
data/entities.py, one Jev call answers all ~30 questions from data/questions.py
as parallel Noul judgments (does this property hold for this entity?).

This keeps the *live* game loop's candidate filtering and question-selection
entropy math exact and instant (plain arithmetic over data/matrix.json) --
the only live Jev calls during a game are the two genuinely fuzzy per-round
decisions (see game.py: which question to ask, and the final guess).

Usage:
    python generate_matrix.py            # build data/matrix.json
    python generate_matrix.py --workers 20
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

from data.entities import ENTITIES
from data.questions import QUESTIONS
from jev_client import call_jev

load_dotenv()

MATRIX_PATH = os.path.join(os.path.dirname(__file__), "data", "matrix.json")


def build_questions(entity_name: str) -> dict:
    return {
        q["id"]: {
            "type": "noul",
            "instructions": q["template"].format(name=entity_name),
            "criteria": {"true": "Yes.", "false": "No."},
        }
        for q in QUESTIONS
    }


def score_entity(entity: dict) -> dict:
    answers = call_jev({"subject": entity["name"]}, build_questions(entity["name"]))
    return {q["id"]: round(answers[q["id"]].get("noul", 0.5), 4) for q in QUESTIONS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()

    print(f"Scoring {len(ENTITIES)} entities x {len(QUESTIONS)} questions "
          f"({args.workers} concurrent workers)...")

    matrix = {}
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(score_entity, e): e for e in ENTITIES}
        for i, future in enumerate(as_completed(futures), start=1):
            entity = futures[future]
            try:
                matrix[entity["id"]] = future.result()
            except Exception as exc:
                errors.append((entity["id"], exc))
            if i % 20 == 0 or i == len(ENTITIES):
                print(f"  {i}/{len(ENTITIES)} done")

    if errors:
        print(f"\n{len(errors)} entities failed to score:")
        for entity_id, exc in errors:
            print(f"  {entity_id}: {exc}")

    with open(MATRIX_PATH, "w") as f:
        json.dump(matrix, f, indent=2, sort_keys=True)
    print(f"\nWrote {len(matrix)} entities to {MATRIX_PATH}")


if __name__ == "__main__":
    main()
