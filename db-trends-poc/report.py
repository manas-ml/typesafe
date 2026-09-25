#!/usr/bin/env python3
"""
Trend analysis over the tickets table -- zero Jev calls in this script.

Section 1 runs over the FULL table using only exact columns (created by
generate_tickets.py, not by Jev) to show what plain SQL already reveals at
full scale (however many rows are in the table).

Section 2 runs over the Jev-enriched subset only (`WHERE jev_analyzed_at IS
NOT NULL`, populated by enrich.py) to show what the cached semantic
judgments add on top of section 1 -- including a shipping-delay trend that's
structurally invisible to section 1 (no raw tag exists for it) and a
churn-risk trend with no exact column at all.

Usage:
    python report.py
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tickets.db")


def in_clause(values: list) -> str:
    return "(" + ",".join("?" * len(values)) + ")"


def section_full_table(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    print(f"=== 1. Full-table stats ({total:,} rows, pure SQL, zero Jev calls) ===\n")

    print("Volume by month (all rows):")
    for month, count in conn.execute("SELECT month, COUNT(*) FROM tickets GROUP BY month ORDER BY month"):
        print(f"  {month}  {count:6,d}")
    print()

    months = [r[0] for r in conn.execute("SELECT DISTINCT month FROM tickets ORDER BY month")]
    prior3, last3 = months[-6:-3], months[-3:]

    print(f"Volume by raw product_area tag: prior 3 months ({', '.join(prior3)}) vs last 3 ({', '.join(last3)}):")
    for tag, in conn.execute("SELECT DISTINCT product_area FROM tickets ORDER BY product_area"):
        prior_n = conn.execute(
            f"SELECT COUNT(*) FROM tickets WHERE product_area = ? AND month IN {in_clause(prior3)}",
            [tag, *prior3],
        ).fetchone()[0]
        last_n = conn.execute(
            f"SELECT COUNT(*) FROM tickets WHERE product_area = ? AND month IN {in_clause(last3)}",
            [tag, *last3],
        ).fetchone()[0]
        change = (last_n - prior_n) / prior_n if prior_n else float("inf")
        print(f"  {tag:16s} prior={prior_n:6,d}  last={last_n:6,d}  change={change:+.0%}")
    print(
        "\n'other' is a grab-bag: this ticket system has no dedicated shipping/\n"
        "delivery tag, so delivery complaints land here mixed in with everything\n"
        "else -- raw-tag SQL alone can't tell whether 'other' is rising because\n"
        "of shipping problems, or something else entirely. See section 2.\n"
    )


def section_enriched(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    enriched = conn.execute("SELECT COUNT(*) FROM tickets WHERE jev_analyzed_at IS NOT NULL").fetchone()[0]
    print(
        f"=== 2. Jev-enriched subset ({enriched:,}/{total:,} rows = {enriched / total:.1%} enriched, "
        "pure SQL over cached judgments) ===\n"
    )
    if enriched == 0:
        print("No rows enriched yet -- run enrich.py first.\n")
        return

    months = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT month FROM tickets WHERE jev_analyzed_at IS NOT NULL ORDER BY month"
        )
    ]
    if len(months) < 6:
        print(f"Only {len(months)} enriched month(s) so far; run enrich.py to cover more months for a clean comparison.\n")
        prior3, last3 = months[: max(len(months) - 3, 0)], months[-3:]
    else:
        prior3, last3 = months[-6:-3], months[-3:]

    print(f"Jev-derived category volume: prior 3 enriched months ({', '.join(prior3)}) vs last 3 ({', '.join(last3)}):")
    for cat, in conn.execute(
        "SELECT DISTINCT jev_category FROM tickets WHERE jev_analyzed_at IS NOT NULL ORDER BY jev_category"
    ):
        prior_n = conn.execute(
            f"SELECT COUNT(*) FROM tickets WHERE jev_category = ? AND month IN {in_clause(prior3)}",
            [cat, *prior3],
        ).fetchone()[0]
        last_n = conn.execute(
            f"SELECT COUNT(*) FROM tickets WHERE jev_category = ? AND month IN {in_clause(last3)}",
            [cat, *last3],
        ).fetchone()[0]
        change = (last_n - prior_n) / prior_n if prior_n else (float("inf") if last_n else 0.0)
        flag = "  <-- structurally invisible in section 1 (was all lumped into 'other')" if cat == "shipping_delivery" else ""
        print(f"  {cat:20s} prior={prior_n:5,d}  last={last_n:5,d}  change={change:+.0%}{flag}")
    print()

    def avg_over(months_subset: list, extra_where: str = "", params: list = None) -> float:
        params = params or []
        query = (
            f"SELECT AVG(jev_sentiment) FROM tickets WHERE jev_analyzed_at IS NOT NULL "
            f"AND month IN {in_clause(months_subset)} {extra_where}"
        )
        return conn.execute(query, [*months_subset, *params]).fetchone()[0] or 0.0

    print("Average sentiment (0=very negative .. 3=positive), prior 3 vs last 3 enriched months:")
    print(f"  prior={avg_over(prior3):.2f}  last={avg_over(last3):.2f}\n")

    print("Churn-risk rate by customer tier, prior 3 vs last 3 enriched months:")
    for tier, in conn.execute("SELECT DISTINCT customer_tier FROM tickets ORDER BY customer_tier"):
        prior_rate = conn.execute(
            f"SELECT AVG(jev_churn_risk) FROM tickets WHERE jev_analyzed_at IS NOT NULL "
            f"AND customer_tier = ? AND month IN {in_clause(prior3)}",
            [tier, *prior3],
        ).fetchone()[0] or 0.0
        last_rate = conn.execute(
            f"SELECT AVG(jev_churn_risk) FROM tickets WHERE jev_analyzed_at IS NOT NULL "
            f"AND customer_tier = ? AND month IN {in_clause(last3)}",
            [tier, *last3],
        ).fetchone()[0] or 0.0
        flag = "  <-- no exact column for this at all; only exists as free text" if tier == "enterprise" else ""
        print(f"  {tier:10s} prior={prior_rate:.0%}  last={last_rate:.0%}{flag}")
    print()

    urgent_prior = conn.execute(
        f"SELECT AVG(jev_urgent) FROM tickets WHERE jev_analyzed_at IS NOT NULL AND month IN {in_clause(prior3)}",
        prior3,
    ).fetchone()[0] or 0.0
    urgent_last = conn.execute(
        f"SELECT AVG(jev_urgent) FROM tickets WHERE jev_analyzed_at IS NOT NULL AND month IN {in_clause(last3)}",
        last3,
    ).fetchone()[0] or 0.0
    print("Urgent-ticket rate, prior 3 vs last 3 enriched months:")
    print(f"  prior={urgent_prior:.0%}  last={urgent_last:.0%}")


def main():
    if not os.path.exists(DB_PATH):
        print(f"{DB_PATH} not found. Run generate_tickets.py first.")
        return
    conn = sqlite3.connect(DB_PATH)
    section_full_table(conn)
    section_enriched(conn)


if __name__ == "__main__":
    main()
