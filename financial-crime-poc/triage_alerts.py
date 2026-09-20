#!/usr/bin/env python3
"""
CLI: triage a batch of AML alerts with TypeSafe's Jev model -- suspicious-
characteristic flags, entity-name resolution, and risk/relevance/evidence
scoring -- then apply a code-owned prioritization and disposition policy.

Usage:
    python triage_alerts.py              # report + top escalations + investigator queue
    python triage_alerts.py --verbose    # also print every alert's result
"""

import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

from jev_client import call_jev

load_dotenv()

ALERTS_PATH = os.path.join(os.path.dirname(__file__), "data", "alerts.json")
MAX_WORKERS = 40
CONFIDENCE_THRESHOLD = 0.5
HAZARD_THRESHOLD = 0.6
PRIORITY_HIGH_THRESHOLD = 5.0
PRIORITY_LOW_THRESHOLD = 2.0

HAZARD_IDS = ["structuring_indicator", "high_risk_jurisdiction", "identity_documentation_gap"]

UNUSUAL_ACTIVITY_LEVELS = [
    "Consistent with the customer's disclosed profile and expected activity.",
    "Mildly unusual, but plausibly explained by ordinary circumstances.",
    "Significantly unusual relative to the customer's disclosed profile.",
    "Highly anomalous; hard to reconcile with any legitimate explanation on file.",
]

EVIDENCE_QUALITY_LEVELS = [
    "Weak/circumstantial: limited supporting detail on file.",
    "Moderate: some supporting detail, but gaps remain.",
    "Strong: well-documented, detailed, and internally consistent.",
]

ALERT_RELEVANCE_LEVELS = [
    "Likely a false positive: matches a known money-laundering pattern only superficially.",
    "Possibly relevant: some genuine indicators, not conclusive.",
    "Highly relevant: strongly consistent with a known money-laundering typology.",
]


def build_questions(candidates: list) -> dict:
    entity_criteria = {
        c["id"]: f"{c['name']} (also known as: {', '.join(c['aliases'])})" for c in candidates
    }
    entity_criteria["no_match"] = "None of the listed candidates plausibly match."

    return {
        "structuring_indicator": {
            "type": "noul",
            "instructions": (
                "Does this transaction pattern suggest structuring -- "
                "breaking a larger amount into pieces to avoid a reporting "
                "threshold?"
            ),
            "criteria": {"true": "Suggests structuring.", "false": "Does not suggest structuring."},
        },
        "high_risk_jurisdiction": {
            "type": "noul",
            "instructions": (
                "Does this alert involve a counterparty or jurisdiction "
                "commonly considered higher risk for money laundering "
                "(e.g. limited beneficial-ownership transparency, no prior "
                "relationship)?"
            ),
            "criteria": {"true": "Involves a high-risk counterparty/jurisdiction.", "false": "Does not."},
        },
        "identity_documentation_gap": {
            "type": "noul",
            "instructions": (
                "Does the KYC documentation on file look incomplete, "
                "inconsistent, or mismatched relative to the transaction "
                "activity described?"
            ),
            "criteria": {"true": "Documentation gap or mismatch present.", "false": "Documentation is adequate and consistent."},
        },
        "unusual_activity": {
            "type": "score",
            "instructions": (
                "How unusual is this transaction activity relative to the "
                "customer's disclosed profile and expected activity?"
            ),
            "criteria": UNUSUAL_ACTIVITY_LEVELS,
        },
        "evidence_quality": {
            "type": "score",
            "instructions": (
                "How strong/well-documented is the evidence behind this "
                "alert (independent of how risky the activity itself is)?"
            ),
            "criteria": EVIDENCE_QUALITY_LEVELS,
        },
        "alert_relevance": {
            "type": "score",
            "instructions": (
                "How relevant is this alert to a genuine money-laundering "
                "typology, as opposed to matching a risk pattern only on "
                "the surface?"
            ),
            "criteria": ALERT_RELEVANCE_LEVELS,
        },
        "entity_match": {
            "type": "choice",
            "instructions": (
                "The alert refers to a customer by the name given in "
                "`mentioned_name`. Which candidate entity does this most "
                "likely refer to, if any?"
            ),
            "criteria": entity_criteria,
        },
    }


def load_alerts() -> list:
    with open(ALERTS_PATH, "r") as f:
        return json.load(f)


def triage_one(alert: dict) -> dict:
    state = {
        "transaction_narrative": alert["transaction_narrative"],
        "kyc_snippet": alert["kyc_snippet"],
        "alert_history_note": alert["alert_history_note"],
        "mentioned_name": alert["mentioned_name"],
        "candidates": [{"id": c["id"], "name": c["name"]} for c in alert["candidates"]],
    }
    questions = build_questions(alert["candidates"])
    answers = call_jev(state, questions)

    hazards = {h: answers[h].get("noul", 0) for h in HAZARD_IDS}
    unusual = answers["unusual_activity"]
    relevance = answers["alert_relevance"]
    evidence = answers["evidence_quality"]
    entity_match = answers["entity_match"]

    risk_confidences = [unusual.get("confidence", 1.0), relevance.get("confidence", 1.0)]
    entity_confidence = entity_match.get("confidence", 1.0)

    if entity_confidence < CONFIDENCE_THRESHOLD:
        disposition = "ROUTE_TO_INVESTIGATOR"
    elif any(c < CONFIDENCE_THRESHOLD for c in risk_confidences):
        disposition = "ROUTE_TO_INVESTIGATOR"
    else:
        priority_score = (
            unusual.get("score", 0) + relevance.get("score", 0) + evidence.get("score", 0)
            + (2.0 if any(v > HAZARD_THRESHOLD for v in hazards.values()) else 0.0)
        )
        if priority_score >= PRIORITY_HIGH_THRESHOLD:
            disposition = "AUTO_ESCALATE"
        elif priority_score <= PRIORITY_LOW_THRESHOLD and not any(v > HAZARD_THRESHOLD for v in hazards.values()):
            disposition = "AUTO_CLOSE"
        else:
            disposition = "STANDARD_QUEUE"
        alert["priority_score"] = priority_score

    return {
        **alert,
        "hazards": hazards,
        "unusual_activity_score": unusual.get("score"),
        "evidence_quality_score": evidence.get("score"),
        "alert_relevance_score": relevance.get("score"),
        "predicted_entity_id": entity_match.get("choice"),
        "entity_match_confidence": entity_confidence,
        "priority_score": alert.get("priority_score"),
        "disposition": disposition,
    }


def triage_all(alerts: list) -> tuple:
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(triage_one, a): a for a in alerts}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append((futures[future]["id"], exc))
            if i % 50 == 0 or i == len(alerts):
                print(f"  {i}/{len(alerts)} done")
    return results, errors


def print_report(results: list, verbose: bool) -> None:
    total = len(results)
    print(f"\n=== Alert Triage Report ({total} alerts) ===\n")

    if verbose:
        for r in sorted(results, key=lambda x: x["id"]):
            print(f"[{r['id']}] disposition={r['disposition']:20s} template={r['template']}")
        print()

    disp_counts = defaultdict(int)
    for r in results:
        disp_counts[r["disposition"]] += 1
    print("Disposition counts:")
    for d in ("AUTO_ESCALATE", "STANDARD_QUEUE", "AUTO_CLOSE", "ROUTE_TO_INVESTIGATOR"):
        count = disp_counts[d]
        print(f"  {d:22s} {count:4d}  ({count / total:.0%})")
    print()

    # Entity-match accuracy (verification only -- true_entity_id never sent to Jev)
    matched = [r for r in results if r["predicted_entity_id"] == r["true_entity_id"]]
    print(f"Entity-match accuracy: {len(matched)}/{total} ({len(matched) / total:.0%})")
    for difficulty in ("exact", "alias", "ambiguous"):
        subset = [r for r in results if r["difficulty"] == difficulty]
        if not subset:
            continue
        correct = sum(1 for r in subset if r["predicted_entity_id"] == r["true_entity_id"])
        routed = sum(1 for r in subset if r["disposition"] == "ROUTE_TO_INVESTIGATOR")
        print(
            f"  {difficulty:10s} {correct}/{len(subset)} correct "
            f"({correct / len(subset):.0%}), {routed} routed to investigator"
        )
    print()

    escalations = sorted(
        [r for r in results if r["disposition"] == "AUTO_ESCALATE"],
        key=lambda r: -(r["priority_score"] or 0),
    )
    print(f"Top AUTO_ESCALATE alerts ({len(escalations)} total):")
    for r in escalations[:15]:
        print(
            f"  [{r['id']}] priority={r['priority_score']:.1f} template={r['template']:28s} "
            f"{r['transaction_narrative'][:70]}..."
        )
    if not verbose and len(escalations) > 15:
        print(f"  ... and {len(escalations) - 15} more (run with --verbose to see all)")
    print()

    investigator_queue = [r for r in results if r["disposition"] == "ROUTE_TO_INVESTIGATOR"]
    print(f"ROUTE_TO_INVESTIGATOR queue ({len(investigator_queue)} total):")
    shown = investigator_queue if verbose else investigator_queue[:15]
    for r in shown:
        reason = "identity ambiguous" if r["entity_match_confidence"] < CONFIDENCE_THRESHOLD else "ambiguous risk read"
        print(f"  [{r['id']}] reason={reason:20s} mentioned_name={r['mentioned_name']}")
    if not verbose and len(investigator_queue) > len(shown):
        print(f"  ... and {len(investigator_queue) - len(shown)} more (run with --verbose to see all)")


def main():
    verbose = "--verbose" in sys.argv

    alerts = load_alerts()
    if not alerts:
        print(f"No alerts found at {ALERTS_PATH}. Run generate_alerts.py first.")
        sys.exit(1)

    print(f"Triaging {len(alerts)} alerts ({MAX_WORKERS} concurrent workers)...")
    results, errors = triage_all(alerts)

    if errors:
        print(f"\n{len(errors)} alert(s) failed to triage:")
        for alert_id, exc in errors:
            print(f"  {alert_id}: {exc}")

    print_report(results, verbose)


if __name__ == "__main__":
    main()
