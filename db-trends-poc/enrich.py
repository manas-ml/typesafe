#!/usr/bin/env python3
"""
Incrementally enrich a sample of not-yet-analyzed rows in the tickets table
with Jev judgments, writing results back onto the same rows. This is the
"enrich once, cache the judgment" pattern: once a row's `jev_analyzed_at` is
set, report.py never calls Jev for it again -- every trend query after this
is pure SQL over cached columns, no matter how large the table gets.

Sampling is stratified per calendar month (not a flat random sample of the
whole table) so every month gets comparable coverage for trend comparison,
even though raw monthly volume differs -- same reasoning as the stratified
sampling in research-trends-poc.

Safe to re-run: each run only ever touches rows still missing
`jev_analyzed_at`, so enrichment accumulates across runs instead of
re-paying for rows already done.

Usage:
    python enrich.py                   # ~50 unanalyzed rows per month (~600 total)
    python enrich.py --per-month 200   # bigger sample
    python enrich.py --all             # enrich every remaining unanalyzed row (expensive at 100k scale -- see README)
"""

import argparse
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from dotenv import load_dotenv

from jev_client import call_jev

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tickets.db")
DEFAULT_WORKERS = 30

CATEGORIES = {
    "billing": "Billing, charges, invoices, refunds, or subscription pricing.",
    "shipping_delivery": "Order shipping, delivery delays, or tracking issues.",
    "account_access": "Login, password, or account-access problems.",
    "product_defect": "A physical product arriving damaged or broken.",
    "praise": "Positive feedback or a compliment, not a problem report.",
    "other": "Doesn't clearly fit any of the above.",
}
SENTIMENT_LEVELS = [
    "Very negative: angry, frustrated, or highly dissatisfied.",
    "Negative: annoyed or dissatisfied, but measured in tone.",
    "Neutral: matter-of-fact, no strong emotion either way.",
    "Positive: satisfied or appreciative.",
]
QUESTIONS = {
    "category": {
        "type": "choice",
        "instructions": (
            "Which category does this support ticket actually belong to, "
            "based on its content? Ignore any existing tag -- judge from "
            "what the ticket actually says."
        ),
        "criteria": CATEGORIES,
    },
    "sentiment": {
        "type": "score",
        "instructions": "What is the customer's emotional tone in this ticket?",
        "criteria": SENTIMENT_LEVELS,
    },
    "urgent": {
        "type": "noul",
        "instructions": "Does this ticket need an urgent, same-day response, as opposed to routine handling?",
        "criteria": {"true": "Needs urgent response.", "false": "Can be handled routinely."},
    },
    "churn_risk": {
        "type": "noul",
        "instructions": "Does this ticket suggest the customer might cancel, downgrade, or switch to a competitor?",
        "criteria": {"true": "Suggests churn risk.", "false": "No indication of churn risk."},
    },
}


def fetch_unanalyzed_sample(conn: sqlite3.Connection, per_month: int) -> list:
    months = [r[0] for r in conn.execute("SELECT DISTINCT month FROM tickets ORDER BY month")]
    rows = []
    for month in months:
        cur = conn.execute(
            "SELECT id, subject, body, product_area FROM tickets "
            "WHERE month = ? AND jev_analyzed_at IS NULL "
            "ORDER BY RANDOM() LIMIT ?",
            (month, per_month),
        )
        rows.extend(cur.fetchall())
    return rows


def analyze_one(row: tuple) -> dict:
    ticket_id, subject, body, product_area = row
    state = {"subject": subject, "body": body, "existing_raw_tag": product_area}
    answers = call_jev(state, QUESTIONS)
    return {
        "id": ticket_id,
        "category": answers["category"].get("choice"),
        "sentiment": answers["sentiment"].get("score"),
        "urgent": answers["urgent"].get("noul"),
        "churn_risk": answers["churn_risk"].get("noul"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-month", type=int, default=50, help="unanalyzed rows to sample per calendar month")
    parser.add_argument("--all", action="store_true", help="enrich every remaining unanalyzed row instead of a per-month sample")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    if args.all:
        rows = conn.execute(
            "SELECT id, subject, body, product_area FROM tickets WHERE jev_analyzed_at IS NULL"
        ).fetchall()
    else:
        rows = fetch_unanalyzed_sample(conn, args.per_month)

    if not rows:
        print("No unanalyzed rows found -- already fully enriched, or run generate_tickets.py first.")
        return

    total_rows = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    already_done = conn.execute("SELECT COUNT(*) FROM tickets WHERE jev_analyzed_at IS NOT NULL").fetchone()[0]
    print(
        f"Enriching {len(rows):,} rows ({args.workers} concurrent workers)... "
        f"[{already_done:,}/{total_rows:,} already enriched before this run]"
    )

    results, errors = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(analyze_one, r): r for r in rows}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append((futures[future][0], exc))
            if i % 100 == 0 or i == len(rows):
                print(f"  {i}/{len(rows)} done")

    if errors:
        print(f"\n{len(errors)} row(s) failed to enrich:")
        for ticket_id, exc in errors:
            print(f"  id={ticket_id}: {exc}")

    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "UPDATE tickets SET jev_category = ?, jev_sentiment = ?, jev_urgent = ?, "
        "jev_churn_risk = ?, jev_analyzed_at = ? WHERE id = ?",
        [(r["category"], r["sentiment"], r["urgent"], r["churn_risk"], now, r["id"]) for r in results],
    )
    conn.commit()

    total_done = conn.execute("SELECT COUNT(*) FROM tickets WHERE jev_analyzed_at IS NOT NULL").fetchone()[0]
    print(
        f"\nWrote {len(results):,} enriched rows to {DB_PATH}. "
        f"Total enriched so far: {total_done:,}/{total_rows:,} ({total_done / total_rows:.1%})."
    )


if __name__ == "__main__":
    main()
