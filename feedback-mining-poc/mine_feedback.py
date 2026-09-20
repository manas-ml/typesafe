#!/usr/bin/env python3
"""
CLI: mine a batch of product reviews with TypeSafe's Jev model.

Map step: one Jev call per review extracting sentiment/topic/actionable/
urgency features. Reduce step: pure code aggregation into a dashboard-style
report. No model call is used for the reduce step.

Usage:
    python mine_feedback.py
"""

import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

from jev_client import call_jev

load_dotenv()

REVIEWS_PATH = os.path.join(os.path.dirname(__file__), "reviews", "reviews.json")
MAX_WORKERS = 40
URGENCY_ESCALATION_THRESHOLD = 2.0
CONFIDENCE_THRESHOLD = 0.5

SENTIMENT_LEVELS = [
    "Very negative: angry, frustrated, or describes a serious negative experience.",
    "Negative: dissatisfied or disappointed, but not extreme.",
    "Neutral: mixed, factual, or no clear positive/negative tone.",
    "Positive: satisfied, appreciative, generally happy with the product.",
    "Very positive: enthusiastic, delighted, strongly recommends the product.",
]

TOPICS = {
    "pricing": "Cost, billing, plan pricing, discounts, or renewal charges.",
    "performance": "Speed, load times, reliability of the product under load.",
    "usability": "Ease of use, UI/UX, discoverability of features.",
    "customer_support": "Interactions with support staff or the support process.",
    "reliability_bugs": "Bugs, crashes, data loss, or things not working as expected.",
    "feature_request": "A request for new functionality that doesn't exist yet.",
    "integrations": "Third-party integrations (Slack, Salesforce, Zapier, etc.).",
    "other": "Doesn't clearly fit any of the above categories.",
}

URGENCY_LEVELS = [
    "No urgency: general comment or praise, nothing needs to happen.",
    "Minor annoyance: worth noting but not blocking anyone.",
    "Significant pain point: actively affecting the customer's ability to use the product well.",
    "Severe/blocking: data loss, incorrect billing/overcharge, security concern, or similar urgent issue.",
]

QUESTIONS = {
    "sentiment": {
        "type": "score",
        "instructions": "What is the overall sentiment expressed in this product review?",
        "criteria": SENTIMENT_LEVELS,
    },
    "topic": {
        "type": "choice",
        "instructions": "What is this product review primarily about?",
        "criteria": TOPICS,
    },
    "actionable_feedback": {
        "type": "noul",
        "instructions": (
            "Does this review contain a concrete bug report or feature "
            "request that the product team should act on?"
        ),
        "criteria": {
            "true": "Describes a specific bug, defect, or missing capability.",
            "false": "General sentiment/praise/complaint with nothing concretely actionable.",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgently should the product/support team address this feedback?",
        "criteria": URGENCY_LEVELS,
    },
}


def load_reviews() -> list:
    with open(REVIEWS_PATH, "r") as f:
        return json.load(f)


def mine_one(review: dict) -> dict:
    state = {"review_text": review["review_text"], "rating_stars": review["rating_stars"]}
    answers = call_jev(state, QUESTIONS)

    sentiment = answers["sentiment"]
    topic = answers["topic"]
    actionable = answers["actionable_feedback"]
    urgency = answers["urgency"]

    is_escalation = (
        urgency.get("score", 0) >= URGENCY_ESCALATION_THRESHOLD
        and urgency.get("confidence", 0) >= CONFIDENCE_THRESHOLD
    )
    needs_review = (
        urgency.get("score", 0) >= URGENCY_ESCALATION_THRESHOLD
        and urgency.get("confidence", 0) < CONFIDENCE_THRESHOLD
    )

    return {
        **review,
        "sentiment_score": sentiment.get("score"),
        "sentiment_confidence": sentiment.get("confidence"),
        "topic": topic.get("choice"),
        "actionable": actionable.get("noul", 0) > 0.5,
        "urgency_score": urgency.get("score"),
        "urgency_confidence": urgency.get("confidence"),
        "is_escalation": is_escalation,
        "needs_review": needs_review,
    }


def mine_all(reviews: list) -> tuple:
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(mine_one, r): r for r in reviews}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append((futures[future]["id"], exc))
            if i % 50 == 0 or i == len(reviews):
                print(f"  {i}/{len(reviews)} done")
    return results, errors


def sentiment_label(score: float) -> str:
    idx = min(max(round(score), 0), len(SENTIMENT_LEVELS) - 1)
    return ["very_negative", "negative", "neutral", "positive", "very_positive"][idx]


def print_report(results: list, verbose: bool = False) -> None:
    total = len(results)
    print(f"\n=== Feedback Mining Report ({total} reviews) ===\n")

    # 1. Sentiment overview
    sentiment_counts = defaultdict(int)
    for r in results:
        sentiment_counts[sentiment_label(r["sentiment_score"])] += 1
    avg_sentiment = sum(r["sentiment_score"] for r in results) / total

    print("Sentiment distribution:")
    for label in ["very_negative", "negative", "neutral", "positive", "very_positive"]:
        count = sentiment_counts[label]
        print(f"  {label:14s} {count:4d}  ({count / total:.0%})")
    print(f"  Average sentiment score (0-4): {avg_sentiment:.2f}\n")

    # 2. Topic breakdown
    by_topic = defaultdict(list)
    for r in results:
        by_topic[r["topic"]].append(r)

    print("Topic breakdown:")
    print(f"  {'topic':18s} {'count':>6s} {'% total':>9s} {'avg sentiment':>14s}")
    topic_stats = {}
    for topic, items in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        avg_sent = sum(i["sentiment_score"] for i in items) / len(items)
        topic_stats[topic] = {"count": len(items), "avg_sentiment": avg_sent, "items": items}
        print(f"  {topic:18s} {len(items):6d} {len(items) / total:8.0%} {avg_sent:14.2f}")
    print()

    # 3. Actionable feedback
    actionable = [r for r in results if r["actionable"]]
    print(f"Actionable feedback: {len(actionable)}/{total} ({len(actionable) / total:.0%})")
    print("  By topic:")
    for topic, stats in topic_stats.items():
        items = stats["items"]
        n_actionable = sum(1 for i in items if i["actionable"])
        print(f"    {topic:18s} {n_actionable}/{len(items)} ({n_actionable / len(items):.0%})")
    print()

    # 4. Escalation list
    escalations = [r for r in results if r["is_escalation"]]
    needs_review = [r for r in results if r["needs_review"]]
    print(f"Escalations (urgency >= {URGENCY_ESCALATION_THRESHOLD:.0f}, confident): {len(escalations)}")
    escalations_sorted = sorted(escalations, key=lambda x: -x["urgency_score"])
    shown = escalations_sorted if verbose else escalations_sorted[:15]
    for r in shown:
        print(
            f"  [{r['id']}] urgency={r['urgency_score']:.1f} topic={r['topic']:16s} "
            f"sentiment={sentiment_label(r['sentiment_score']):13s} "
            f"{r['review_text'][:80]}..."
        )
    if not verbose and len(escalations_sorted) > len(shown):
        print(f"  ... and {len(escalations_sorted) - len(shown)} more (run with --verbose to see all)")

    print("\n  Escalations by topic:")
    esc_by_topic = defaultdict(int)
    for r in escalations:
        esc_by_topic[r["topic"]] += 1
    for topic, count in sorted(esc_by_topic.items(), key=lambda kv: -kv[1]):
        print(f"    {topic:18s} {count}")
    if needs_review:
        print(f"\nNEEDS_HUMAN_REVIEW (high urgency, low confidence): {len(needs_review)}")
        for r in needs_review:
            print(f"  [{r['id']}] urgency={r['urgency_score']:.1f} confidence={r['urgency_confidence']:.2f}")
    print()

    # 5. Derived insight lines (pure code, computed from the aggregates above)
    negative_topics = {
        t: s for t, s in topic_stats.items() if s["avg_sentiment"] < avg_sentiment
    }
    if negative_topics:
        worst_topic = min(negative_topics, key=lambda t: negative_topics[t]["avg_sentiment"])
        print(
            f"Insight: '{worst_topic}' has the lowest average sentiment "
            f"({negative_topics[worst_topic]['avg_sentiment']:.2f}) among all topics."
        )
    best_topic = max(topic_stats, key=lambda t: topic_stats[t]["avg_sentiment"])
    print(
        f"Insight: '{best_topic}' has the highest average sentiment "
        f"({topic_stats[best_topic]['avg_sentiment']:.2f})."
    )
    if escalations:
        top_escalation_topic = max(
            {r["topic"] for r in escalations},
            key=lambda t: sum(1 for r in escalations if r["topic"] == t),
        )
        print(f"Insight: most escalations come from the '{top_escalation_topic}' topic.")


def main():
    verbose = "--verbose" in sys.argv

    reviews = load_reviews()
    if not reviews:
        print(f"No reviews found at {REVIEWS_PATH}. Run generate_reviews.py first.")
        sys.exit(1)

    print(f"Mining {len(reviews)} reviews ({MAX_WORKERS} concurrent workers)...")
    results, errors = mine_all(reviews)

    if errors:
        print(f"\n{len(errors)} review(s) failed to mine:")
        for review_id, exc in errors:
            print(f"  {review_id}: {exc}")

    print_report(results, verbose)


if __name__ == "__main__":
    main()
