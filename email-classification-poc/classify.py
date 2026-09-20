#!/usr/bin/env python3
"""
CLI: classify a batch of sample emails into spam / not_spam / important using
TypeSafe's Jev model, then route each to an action.

Usage:
    python classify.py              # summary + misclassifications only
    python classify.py --verbose    # print every email's result
"""

import glob
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

from jev_client import call_jev

load_dotenv()

EMAILS_DIR = os.path.join(os.path.dirname(__file__), "emails")
LABELS = ("spam", "important", "not_spam")
MAX_WORKERS = 300
CONFIDENCE_REVIEW_THRESHOLD = 0.5

HEADER_RE = re.compile(r"^(From|Subject):\s*(.*)$", re.MULTILINE)

QUESTION = {
    "category": {
        "type": "choice",
        "instructions": (
            "Classify this email into exactly one category based on its "
            "sender, subject, and body content."
        ),
        "criteria": {
            "spam": "Unsolicited scam/commercial content: phishing, prize "
            "scams, fake invoices, dubious offers with no genuine "
            "relationship to the recipient.",
            "important": "Legitimate email that is time-sensitive or "
            "high-stakes: urgent requests from colleagues/managers, "
            "security alerts, outages, deadlines, contracts needing "
            "signature.",
            "not_spam": "Legitimate email that is not urgent: newsletters, "
            "routine notifications, receipts, non-time-sensitive updates.",
        },
    }
}

ACTIONS = {
    "spam": "Move to Spam folder",
    "important": "Flag + notify",
    "not_spam": "Deliver to Inbox",
}


def parse_email(path: str) -> dict:
    with open(path, "r") as f:
        text = f.read()

    headers = dict(HEADER_RE.findall(text))
    body = text.split("\n\n", 1)[1] if "\n\n" in text else ""

    return {
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "body": body.strip(),
    }


def load_dataset() -> list:
    dataset = []
    for label in LABELS:
        for path in sorted(glob.glob(os.path.join(EMAILS_DIR, label, "*.txt"))):
            dataset.append({"path": path, "true_label": label, "email": parse_email(path)})
    return dataset


def classify_one(item: dict) -> dict:
    answers = call_jev(item["email"], QUESTION)
    answer = answers["category"]
    predicted = answer["choice"]
    confidence = answer.get("confidence", 0.0)

    if confidence < CONFIDENCE_REVIEW_THRESHOLD:
        action = "NEEDS_REVIEW"
    else:
        action = ACTIONS[predicted]

    return {
        **item,
        "predicted": predicted,
        "confidence": confidence,
        "probabilities": answer.get("probabilities", {}),
        "action": action,
    }


def print_results(results: list, verbose: bool) -> None:
    correct = 0
    confusion = {t: {p: 0 for p in LABELS} for t in LABELS}
    conf_correct, conf_incorrect = [], []
    misclassified = []

    for r in results:
        is_correct = r["predicted"] == r["true_label"]
        correct += is_correct
        confusion[r["true_label"]][r["predicted"]] += 1
        (conf_correct if is_correct else conf_incorrect).append(r["confidence"])
        if not is_correct:
            misclassified.append(r)

        if verbose:
            mark = "✓" if is_correct else "✗"
            print(
                f"{mark} {os.path.basename(r['path']):32s} "
                f"true={r['true_label']:10s} predicted={r['predicted']:10s} "
                f"confidence={r['confidence']:.2f}  action={r['action']}"
            )

    if not verbose and misclassified:
        print(f"Misclassified ({len(misclassified)}):")
        for r in misclassified:
            print(
                f"  {os.path.basename(r['path']):32s} "
                f"true={r['true_label']:10s} predicted={r['predicted']:10s} "
                f"confidence={r['confidence']:.2f}"
            )
        print()

    total = len(results)
    print(f"Accuracy: {correct}/{total} ({correct / total:.0%})")

    print()
    print("Confusion matrix (rows = true label, columns = predicted):")
    header = " " * 12 + "".join(f"{p:>12s}" for p in LABELS)
    print(header)
    for t in LABELS:
        row = "".join(f"{confusion[t][p]:>12d}" for p in LABELS)
        print(f"{t:12s}{row}")

    def avg(values):
        return sum(values) / len(values) if values else float("nan")

    print()
    print(f"Avg confidence on correct predictions:   {avg(conf_correct):.2f}")
    print(f"Avg confidence on incorrect predictions: {avg(conf_incorrect):.2f}")


def main():
    verbose = "--verbose" in sys.argv

    dataset = load_dataset()
    if not dataset:
        print(f"No emails found under {EMAILS_DIR}")
        return

    print(f"Classifying {len(dataset)} emails ({MAX_WORKERS} concurrent workers)...")

    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(classify_one, item): item for item in dataset}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append((futures[future]["path"], exc))
            if i % 50 == 0 or i == len(dataset):
                print(f"  {i}/{len(dataset)} done")

    if errors:
        print(f"\n{len(errors)} email(s) failed to classify:")
        for path, exc in errors:
            print(f"  {path}: {exc}")

    results.sort(key=lambda r: r["path"])
    print()
    print_results(results, verbose)


if __name__ == "__main__":
    main()
