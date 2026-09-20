#!/usr/bin/env python3
"""
Generate a synthetic dataset of product reviews for the feedback-mining POC.

Wipes and regenerates reviews/reviews.json using a set of randomized templates
spanning realistic SaaS-product review scenarios, so the dataset can be scaled
up without hand-authoring each one.

Usage:
    python generate_reviews.py [--items 300] [--seed 42]
"""

import argparse
import json
import os
import random

from faker import Faker

REVIEWS_PATH = os.path.join(os.path.dirname(__file__), "reviews", "reviews.json")


def pricing_complaint(fake):
    plan = random.choice(["Pro", "Team", "Business"])
    pct = random.randint(20, 80)
    return (
        random.randint(1, 2),
        f"The {plan} plan price jumped {pct}% at renewal with zero warning. "
        f"We've been customers for {random.randint(1, 4)} years and this "
        f"feels like a bait and switch. Seriously reconsidering our renewal.",
    )


def billing_overcharge_urgent(fake):
    amount = round(random.uniform(200, 4000), 2)
    return (
        1,
        f"We were charged ${amount:,.2f} extra this month with no "
        f"explanation - looks like we got billed for seats we cancelled "
        f"months ago. This needs to be refunded immediately, it's affecting "
        f"our accounting close. Nobody has responded to my emails in "
        f"{random.randint(3, 10)} days.",
    )


def performance_praise(fake):
    pct = random.randint(30, 70)
    return (
        5,
        f"Huge improvement in load times since the last update - our "
        f"dashboards that used to take forever now load in seconds. Feels "
        f"like a {pct}% speedup. Whatever the team changed, keep it up.",
    )


def generic_positive(fake):
    return (
        5,
        f"Been using this for {random.randint(1, 3)} years now and it just "
        f"works. Solid product, does what it says, support has always been "
        f"responsive when we needed them. Happy to recommend it to others.",
    )


def usability_confusion(fake):
    feature = fake.bs()
    return (
        3,
        f"Took our team a while to figure out how to set up {feature} - the "
        f"settings are scattered across three different menus and it's not "
        f"obvious where to configure it. Works fine once you find it, but "
        f"the UX could really use a pass.",
    )


def support_praise(fake):
    return (
        5,
        f"Had an issue over the weekend and support got back to us in under "
        f"{random.randint(5, 30)} minutes, even resolved it same day. That "
        f"kind of responsiveness is rare these days.",
    )


def support_complaint(fake):
    days = random.randint(4, 14)
    return (
        2,
        f"Opened a support ticket {days} days ago and still haven't heard "
        f"back beyond the auto-reply. This is a paid plan, we shouldn't have "
        f"to wait this long for a response on a basic question.",
    )


def bug_report(fake):
    feature = fake.bs()
    return (
        2,
        f"Found a bug where the {feature} feature silently fails and drops "
        f"data when you have more than {random.randint(50, 500)} records in "
        f"a batch - no error message, it just doesn't save. Lost a chunk of "
        f"work before we noticed. Please fix, this is a data integrity issue.",
    )


def feature_request(fake):
    feature = fake.bs()
    return (
        4,
        f"Would love to see support for {feature} added - we're currently "
        f"working around it with a clunky export/import process. Otherwise "
        f"really happy with the product, this would just make it even "
        f"better for our workflow.",
    )


def integration_issue(fake):
    tool = random.choice(["Slack", "Salesforce", "Zapier", "HubSpot", "Jira"])
    return (
        2,
        f"The {tool} integration keeps disconnecting every few days and we "
        f"have to manually reauthorize it. Been happening since the last "
        f"couple of releases. Kind of defeats the purpose of having an "
        f"integration if we have to babysit it.",
    )


TEMPLATES = [
    pricing_complaint, billing_overcharge_urgent, performance_praise,
    generic_positive, usability_confusion, support_praise, support_complaint,
    bug_report, feature_request, integration_issue,
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    fake = Faker()
    Faker.seed(args.seed)

    reviews = []
    for i in range(args.items):
        template = TEMPLATES[i % len(TEMPLATES)]
        stars, text = template(fake)
        reviews.append(
            {
                "id": f"r{i:04d}",
                "template": template.__name__,
                "rating_stars": stars,
                "review_text": text,
            }
        )

    random.shuffle(reviews)

    os.makedirs(os.path.dirname(REVIEWS_PATH), exist_ok=True)
    with open(REVIEWS_PATH, "w") as f:
        json.dump(reviews, f, indent=2)

    print(f"Generated {len(reviews)} reviews -> {REVIEWS_PATH}")


if __name__ == "__main__":
    main()
