#!/usr/bin/env python3
"""
Build a synthetic, deliberately-patterned support-ticket table in local
SQLite -- large enough (default 100k rows) that "just run Jev on every row"
is obviously the wrong approach, which is the point of this POC.

Three patterns are planted so enrich.py + report.py have something real to
recover:

  1. `billing` complaints (raw tag is accurate) rise over the last 3 months --
     a trend plain SQL on the exact tag already shows on its own.
  2. Shipping/delivery complaints have NO dedicated raw tag in this ticket
     system (a realistic legacy-schema gap) -- they're always logged as
     `other`, and they spike hard in the very last month. Raw-tag SQL can't
     see this at all (section 1 of report.py); only Jev's own reading of the
     ticket body recovers it as its own category (section 2).
  3. Enterprise-tier tickets increasingly contain churn-risk language
     ("considering canceling", "evaluating alternatives") in the last 2
     months -- there is no exact column for this at all; it only exists as
     free text, so only a semantic read can surface it.

Usage:
    python generate_tickets.py --rows 100000 --seed 42
"""

import argparse
import os
import random
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tickets.db")
MONTHS = 12  # month_index 0 = oldest .. MONTHS-1 = most recent
BATCH_SIZE = 5000

PLANS = ["Starter", "Pro", "Team", "Enterprise Plus"]
PRODUCTS = ["wireless headphones", "smart speaker", "fitness tracker", "laptop stand", "4K monitor"]

BILLING_TEMPLATES = [
    "I was charged twice for my {plan} subscription this month -- can you refund the duplicate charge?",
    "My invoice shows the wrong amount for {plan}, it doesn't match what I signed up for.",
    "Why did my subscription price go up without any notice?",
    "Please cancel my {plan} plan and refund this billing cycle, I was charged in error.",
]
SHIPPING_TEMPLATES = [
    "My order #{order_id} was supposed to arrive last week and there's still no tracking update.",
    "It's been over 10 days and my package hasn't even shipped yet.",
    "Where is my order? The estimated delivery date has already passed.",
    "Tracking says 'label created' for over a week now with no movement at all.",
]
ACCOUNT_TEMPLATES = [
    "I can't log into my account, it keeps saying invalid password even after a reset.",
    "My account got locked after too many login attempts, please help me regain access.",
    "I'm not receiving the two-factor login code by email or text.",
]
DEFECT_TEMPLATES = [
    "The {product} I received stopped working after two days of use.",
    "There's a visible crack in the {product} I just unboxed.",
    "My {product} won't power on at all out of the box.",
]
PRAISE_TEMPLATES = [
    "Just wanted to say your support team was fantastic and resolved my issue quickly!",
    "Love the new {product}, works great, no complaints at all.",
    "Fast shipping and great quality, very happy with this purchase.",
]
GENERIC_TEMPLATES = [
    "Do you offer a student discount on any plans?",
    "Can I change the email address on my account?",
    "What's your return policy on a {product}?",
    "Just checking on the status of a request I submitted a while back.",
]
CHURN_CLAUSES = [
    " We are seriously considering canceling our {plan} plan and moving to a competitor if this isn't resolved soon.",
    " This is the third issue this month -- we may not renew our contract.",
    " Extremely disappointed with the reliability lately; we're evaluating alternatives.",
]

SUBJECTS = {
    "billing": ["Duplicate charge on my account", "Incorrect invoice amount", "Question about a price change"],
    "shipping": ["Order delayed", "Where is my package?", "No tracking movement"],
    "account_access": ["Can't log in", "Account locked", "Not receiving 2FA code"],
    "product_defect": ["Item arrived damaged", "Product stopped working", "Defective on arrival"],
    "praise": ["Great support experience", "Really happy with my order", "Thank you!"],
    "generic": ["Quick question", "Follow-up on my request", "General inquiry"],
}


def month_start(now: datetime, months_ago: int) -> datetime:
    total = now.year * 12 + (now.month - 1) - months_ago
    year, month0 = divmod(total, 12)
    return datetime(year, month0 + 1, 1)


def random_datetime_in_month(start: datetime) -> datetime:
    total = start.year * 12 + (start.month - 1) + 1
    year, month0 = divmod(total, 12)
    next_start = datetime(year, month0 + 1, 1)
    span = int((next_start - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, span - 1))


def ramp(month_index: int, over_last: int) -> float:
    """0..1 linear ramp over the last `over_last` months (of MONTHS total)."""
    start = MONTHS - over_last
    if month_index < start:
        return 0.0
    return min((month_index - start + 1) / over_last, 1.0)


def category_weights(month_index: int) -> dict:
    ramp3 = ramp(month_index, 3)
    ramp2 = ramp(month_index, 2)
    w = {
        "billing": 0.15 + 0.15 * ramp3,
        "shipping": 0.05 + 0.20 * ramp2,
        "account_access": 0.15,
        "product_defect": 0.15,
        "praise": 0.10,
        "generic": 0.15,
    }
    total = sum(w.values())
    return {k: v / total for k, v in w.items()}


RAW_TAG = {
    "billing": "billing",
    "shipping": "other",  # no dedicated shipping tag exists in this ticket system
    "account_access": "account_access",
    "product_defect": "product_defect",
    "praise": "praise",
    "generic": "other",
}
TEMPLATES = {
    "billing": BILLING_TEMPLATES,
    "shipping": SHIPPING_TEMPLATES,
    "account_access": ACCOUNT_TEMPLATES,
    "product_defect": DEFECT_TEMPLATES,
    "praise": PRAISE_TEMPLATES,
    "generic": GENERIC_TEMPLATES,
}


def build_ticket(month_index: int, month_dt_start: datetime) -> tuple:
    weights = category_weights(month_index)
    category = random.choices(list(weights), weights=list(weights.values()))[0]

    plan = random.choice(PLANS)
    product = random.choice(PRODUCTS)
    order_id = f"{random.randint(100000, 999999)}"

    body = random.choice(TEMPLATES[category]).format(plan=plan, product=product, order_id=order_id)
    subject = random.choice(SUBJECTS[category])

    customer_tier = random.choices(["free", "pro", "enterprise"], weights=[0.6, 0.3, 0.1])[0]
    channel = random.choices(["email", "chat", "phone", "social"], weights=[0.45, 0.35, 0.15, 0.05])[0]

    churn_p = (0.03 + 0.25 * ramp(month_index, 2)) if customer_tier == "enterprise" else 0.02
    if random.random() < churn_p:
        body += random.choice(CHURN_CLAUSES).format(plan=plan)

    created_at = random_datetime_in_month(month_dt_start)
    month_str = f"{created_at.year:04d}-{created_at.month:02d}"

    return (
        created_at.isoformat(),
        month_str,
        channel,
        customer_tier,
        RAW_TAG[category],
        subject,
        body,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    now = datetime.now()

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            month TEXT NOT NULL,
            channel TEXT NOT NULL,
            customer_tier TEXT NOT NULL,
            product_area TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            jev_category TEXT,
            jev_sentiment REAL,
            jev_urgent REAL,
            jev_churn_risk REAL,
            jev_analyzed_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX idx_tickets_month ON tickets(month)")
    conn.execute("CREATE INDEX idx_tickets_analyzed ON tickets(jev_analyzed_at)")

    # mild month-over-month growth in raw volume, oldest -> newest
    month_weights = [1.0 + 0.04 * i for i in range(MONTHS)]
    total_weight = sum(month_weights)
    rows_per_month = [round(args.rows * w / total_weight) for w in month_weights]

    print(f"Generating {sum(rows_per_month):,} tickets across {MONTHS} months into {DB_PATH}...")

    batch = []
    inserted = 0
    for month_index in range(MONTHS):
        months_ago = (MONTHS - 1) - month_index
        month_dt_start = month_start(now, months_ago)
        for _ in range(rows_per_month[month_index]):
            batch.append(build_ticket(month_index, month_dt_start))
            if len(batch) >= BATCH_SIZE:
                conn.executemany(
                    "INSERT INTO tickets (created_at, month, channel, customer_tier, product_area, subject, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    batch,
                )
                inserted += len(batch)
                batch = []
                print(f"  {inserted:,} rows inserted")
    if batch:
        conn.executemany(
            "INSERT INTO tickets (created_at, month, channel, customer_tier, product_area, subject, body) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            batch,
        )
        inserted += len(batch)

    conn.commit()
    print(f"\nDone: {inserted:,} rows in {DB_PATH}")

    print("\nRows per month:")
    for month, count in conn.execute("SELECT month, COUNT(*) FROM tickets GROUP BY month ORDER BY month"):
        print(f"  {month}  {count:,}")


if __name__ == "__main__":
    main()
