#!/usr/bin/env python3
"""
CLI: AI-assisted code review triage powered by TypeSafe's Jev model.

Usage:
    python review.py fixtures/risky_change.diff
    python review.py --all
"""

import glob
import os
import re
import sys

from dotenv import load_dotenv

from jev_client import call_jev

load_dotenv()

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

SECURITY_RISK_LEVELS = [
    "No security concern.",
    "Minor concern (e.g. slightly loose input handling), unlikely to be exploitable.",
    "Moderate risk that needs a security-focused review before merge (e.g. "
    "unvalidated input reaching a sensitive sink, weak auth check).",
    "Severe / blocking risk (e.g. hardcoded secret or credential, SQL/command "
    "injection, disabled or removed authentication/authorization check).",
]

CORRECTNESS_RISK_LEVELS = [
    "No apparent correctness issue.",
    "Minor bug potential (e.g. an edge case that might not be handled).",
    "Likely bug: probably produces wrong behavior in common cases.",
    "Breaking bug: this change looks like it would break existing functionality.",
]

QUESTIONS = {
    "security_risk": {
        "type": "score",
        "instructions": (
            "Given this code diff, how much security risk does the change "
            "introduce or leave unaddressed?"
        ),
        "criteria": SECURITY_RISK_LEVELS,
    },
    "correctness_risk": {
        "type": "score",
        "instructions": (
            "Given this code diff, how likely is it that the change introduces "
            "or leaves a correctness bug?"
        ),
        "criteria": CORRECTNESS_RISK_LEVELS,
    },
    "breaking_change": {
        "type": "noul",
        "instructions": (
            "Does this diff change a public/external contract (function "
            "signature, API response shape, CLI flag, config format, etc.) in "
            "a backward-incompatible way?"
        ),
        "criteria": {
            "true": "A public/external contract changed in a way old callers "
            "would break against.",
            "false": "No public/external contract changed incompatibly.",
        },
    },
    "needs_tests": {
        "type": "noul",
        "instructions": (
            "Does this diff add non-trivial logic (new branches, new "
            "computation, new error handling) without adding or updating any "
            "corresponding test code?"
        ),
        "criteria": {
            "true": "Non-trivial logic was added/changed with no accompanying "
            "test changes.",
            "false": "Either there's no non-trivial new logic, or tests were "
            "added/updated alongside it.",
        },
    },
}

CONFIDENCE_ESCALATION_THRESHOLD = 0.5
RISK_BLOCK_THRESHOLD = 2.0
NOUL_FLAG_THRESHOLD = 0.6

FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


def build_state(diff_text: str) -> dict:
    changed_files = FILE_HEADER_RE.findall(diff_text)
    return {"diff": diff_text, "changed_files": changed_files}


def decide(answers: dict) -> tuple:
    """Apply the code-owned decision policy to Jev's raw answers.

    Returns (verdict, flags: list[str]).
    """
    security = answers.get("security_risk", {})
    correctness = answers.get("correctness_risk", {})
    breaking = answers.get("breaking_change", {})
    needs_tests = answers.get("needs_tests", {})

    security_score = security.get("score", 0)
    security_conf = security.get("confidence", 1.0)
    correctness_score = correctness.get("score", 0)
    correctness_conf = correctness.get("confidence", 1.0)

    flags = []

    low_confidence = (
        security_conf < CONFIDENCE_ESCALATION_THRESHOLD
        or correctness_conf < CONFIDENCE_ESCALATION_THRESHOLD
    )

    if low_confidence:
        verdict = "NEEDS_HUMAN_REVIEW"
        flags.append(
            "Low model confidence on risk scoring -- routed to a human reviewer "
            "instead of trusting the score."
        )
    elif security_score >= RISK_BLOCK_THRESHOLD or correctness_score >= RISK_BLOCK_THRESHOLD:
        verdict = "REQUEST_CHANGES"
    else:
        verdict = "AUTO_APPROVE"

    if breaking.get("noul", 0) > NOUL_FLAG_THRESHOLD:
        flags.append(
            "Possible breaking change -- consider a changelog entry / major version bump."
        )
    if needs_tests.get("noul", 0) > NOUL_FLAG_THRESHOLD:
        flags.append("New logic without accompanying tests -- consider adding tests.")

    return verdict, flags


def format_report(path: str, answers: dict, verdict: str, flags: list) -> str:
    lines = [f"=== {os.path.basename(path)} ===", f"Verdict: {verdict}"]

    for qid in ("security_risk", "correctness_risk"):
        a = answers.get(qid, {})
        lines.append(
            f"  {qid}: score={a.get('score')} confidence={a.get('confidence')}"
        )
    for qid in ("breaking_change", "needs_tests"):
        a = answers.get(qid, {})
        lines.append(f"  {qid}: noul={a.get('noul')}")

    if flags:
        lines.append("  Flags:")
        for f in flags:
            lines.append(f"    - {f}")

    return "\n".join(lines)


def review_file(path: str) -> None:
    with open(path, "r") as f:
        diff_text = f.read()

    state = build_state(diff_text)
    answers = call_jev(state, QUESTIONS)
    verdict, flags = decide(answers)
    print(format_report(path, answers, verdict, flags))
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--all":
        paths = sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.diff")))
        if not paths:
            print(f"No .diff files found in {FIXTURES_DIR}")
            sys.exit(1)
        for path in paths:
            review_file(path)
    else:
        review_file(sys.argv[1])


if __name__ == "__main__":
    main()
