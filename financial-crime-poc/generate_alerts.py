#!/usr/bin/env python3
"""
Generate a synthetic entity registry and AML alert dataset for the financial
crime triage POC.

Content note: narratives describe abstract transaction *patterns* (amounts,
timing, jurisdictions) for classifier testing, the same kind of fixture used
in real AML software demos/training data -- no real entities, no real PII
(names/SSNs/addresses are all Faker-generated), no operational guidance on
evading detection.

Usage:
    python generate_alerts.py [--entities 15] [--alerts 150] [--seed 42]
"""

import argparse
import json
import os
import random

from faker import Faker

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
REGISTRY_PATH = os.path.join(DATA_DIR, "entity_registry.json")
ALERTS_PATH = os.path.join(DATA_DIR, "alerts.json")

NICKNAMES = {
    "Robert": "Bob", "William": "Bill", "Richard": "Rick", "James": "Jim",
    "Michael": "Mike", "Elizabeth": "Liz", "Katherine": "Kathy",
    "Jennifer": "Jen", "Christopher": "Chris", "Anthony": "Tony",
    "Patricia": "Pat", "Margaret": "Maggie", "Charles": "Chuck",
}

HIGH_RISK_COUNTRIES = ["Cyprus", "Malta", "Panama", "the UAE", "Macau"]
NORMAL_COUNTRIES = ["Canada", "Germany", "Japan", "Australia", "the UK"]


def make_individual(fake):
    first, last = fake.first_name(), fake.last_name()
    canonical = f"{first} {last}"
    if random.random() < 0.5 and first in NICKNAMES:
        alias = f"{NICKNAMES[first]} {last}"
    elif random.random() < 0.5:
        alias = f"{first} {fake.last_name()}"  # e.g. maiden/married name change
    else:
        alias = f"{first} {last[:-1]}"  # simple typo: dropped last letter
    return {
        "type": "individual",
        "canonical_name": canonical,
        "aliases": [alias],
        "occupation": fake.job(),
    }


def make_business(fake):
    canonical = fake.company()
    suffix = canonical.split()[-1] if " " in canonical else "LLC"
    base = canonical.rsplit(" ", 1)[0] if " " in canonical else canonical
    alias = random.choice([f"{base}", f"{base[:3].upper()}", f"{base} Group"])
    return {
        "type": "business",
        "canonical_name": canonical,
        "aliases": [alias],
        "occupation": fake.bs() + " services",
    }


def build_registry(n, fake):
    registry = []
    for i in range(n):
        maker = make_individual if i % 3 != 0 else make_business
        entity = maker(fake)
        entity["id"] = f"E{i:03d}"
        registry.append(entity)
    return registry


# ---------------------------------------------------------------------------
# Alert narrative templates
# ---------------------------------------------------------------------------

def structuring_pattern(fake, entity):
    n = random.randint(4, 9)
    amount = random.randint(9200, 9900)
    days = random.randint(7, 14)
    narrative = (
        f"Account received {n} separate cash deposits of ${amount:,} each "
        f"over {days} days, each just under the $10,000 currency transaction "
        f"reporting threshold, from {n} different branch locations."
    )
    return narrative, "high"


def high_risk_jurisdiction_wire(fake, entity):
    country = random.choice(HIGH_RISK_COUNTRIES)
    amount = random.randint(50000, 400000)
    narrative = (
        f"Account received an incoming wire of ${amount:,} from a "
        f"counterparty in {country}, a jurisdiction with limited beneficial-"
        f"ownership transparency, with no prior transaction history between "
        f"the parties."
    )
    return narrative, "high"


def shell_company_mismatch(fake, entity):
    amount = random.randint(80000, 500000)
    narrative = (
        f"Business account for a small consulting firm with 2 disclosed "
        f"employees received ${amount:,} in international wires this "
        f"quarter, inconsistent with the stated scale of consulting "
        f"revenue on file; registered address matches a residential "
        f"mail-forwarding service."
    )
    return narrative, "high"


def rapid_fund_movement(fake, entity):
    amount = random.randint(20000, 150000)
    hours = random.randint(1, 6)
    narrative = (
        f"Account received ${amount:,} and forwarded substantially the same "
        f"amount to a third-party account within {hours} hours, with no "
        f"apparent business purpose disclosed for either leg."
    )
    return narrative, "high"


def false_positive_payroll(fake, entity):
    amount = random.randint(2000, 4500)
    narrative = (
        f"Account received a recurring biweekly deposit of ${amount:,} "
        f"labeled with the customer's disclosed employer's payroll "
        f"reference, consistent with 18 months of prior deposit history."
    )
    return narrative, "low"


def false_positive_business_growth(fake, entity):
    pct = random.randint(20, 60)
    country = random.choice(NORMAL_COUNTRIES)
    narrative = (
        f"Business account deposit volume increased {pct}% this quarter, "
        f"consistent with the disclosed seasonal sales pattern and a new "
        f"wholesale contract with a buyer in {country}; invoices and "
        f"shipping documentation are on file for each deposit."
    )
    return narrative, "low"


def false_positive_family_transfer(fake, entity):
    amount = random.randint(500, 3000)
    narrative = (
        f"Account received a ${amount:,} incoming transfer labeled as a "
        f"family gift from a relative previously disclosed on the "
        f"customer's KYC profile, consistent with occasional prior "
        f"transfers from the same sender."
    )
    return narrative, "low"


def genuine_kyc_gap_but_legit(fake, entity):
    amount = random.randint(10000, 40000)
    narrative = (
        f"Account received a ${amount:,} deposit described as proceeds "
        f"from a personal property sale; supporting documentation "
        f"(sale agreement) was requested but has not yet been provided by "
        f"the customer, though the amount is broadly consistent with "
        f"disclosed asset holdings."
    )
    return narrative, "medium"


NARRATIVE_TEMPLATES = [
    structuring_pattern, high_risk_jurisdiction_wire, shell_company_mismatch,
    rapid_fund_movement, false_positive_payroll, false_positive_business_growth,
    false_positive_family_transfer, genuine_kyc_gap_but_legit,
]


def make_kyc_snippet(fake, entity):
    return (
        f"On-file profile: {entity['type']} customer, stated occupation/"
        f"activity: {entity['occupation']}. Customer since "
        f"{fake.date_between(start_date='-8y', end_date='-1y')}."
    )


def make_alert_history_note(fake):
    return random.choice(
        [
            "First alert on this customer in the past 12 months.",
            "Second alert on this customer in 90 days; the prior alert was closed as a false positive.",
            "Third alert on this customer in 90 days; two prior alerts were closed as false positives.",
            "This customer had a prior alert that was escalated and resulted in a filed SAR.",
            "No prior alert history for this customer.",
        ]
    )


def pick_mentioned_name(entity, difficulty, registry, fake):
    """Return (mentioned_name, candidates: list[entity dicts])."""
    same_type = [e for e in registry if e["type"] == entity["type"] and e["id"] != entity["id"]]
    decoys = random.sample(same_type, k=min(2, len(same_type)))

    if difficulty == "exact":
        mentioned_name = entity["canonical_name"]
        candidates = [entity] + decoys
    elif difficulty == "alias":
        mentioned_name = entity["aliases"][0]
        candidates = [entity] + decoys
    else:  # ambiguous: blend the true entity with one decoy so the name is genuinely confusable
        decoy = decoys[0]
        if entity["type"] == "individual":
            true_first = entity["canonical_name"].split()[0]
            decoy_last = decoy["canonical_name"].split()[-1]
            mentioned_name = f"{true_first} {decoy_last}"
        else:
            true_word = entity["canonical_name"].split()[0]
            decoy_word = decoy["canonical_name"].split()[-1]
            mentioned_name = f"{true_word} {decoy_word}"
        third = random.choice([e for e in registry if e["id"] not in (entity["id"], decoy["id"])])
        candidates = [entity, decoy, third]

    random.shuffle(candidates)
    return mentioned_name, candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entities", type=int, default=15)
    parser.add_argument("--alerts", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    fake = Faker()
    Faker.seed(args.seed)

    registry = build_registry(args.entities, fake)

    alerts = []
    for i in range(args.alerts):
        entity = random.choice(registry)
        template = NARRATIVE_TEMPLATES[i % len(NARRATIVE_TEMPLATES)]
        narrative, _risk_tier = template(fake, entity)

        difficulty = random.choices(
            ["exact", "alias", "ambiguous"], weights=[0.4, 0.3, 0.3]
        )[0]
        mentioned_name, candidates = pick_mentioned_name(entity, difficulty, registry, fake)

        alerts.append(
            {
                "id": f"A{i:04d}",
                "template": template.__name__,
                "difficulty": difficulty,
                "transaction_narrative": narrative,
                "kyc_snippet": make_kyc_snippet(fake, entity),
                "alert_history_note": make_alert_history_note(fake),
                "mentioned_name": mentioned_name,
                "candidates": [
                    {"id": c["id"], "name": c["canonical_name"], "aliases": c["aliases"]}
                    for c in candidates
                ],
                "true_entity_id": entity["id"],
            }
        )

    random.shuffle(alerts)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)
    with open(ALERTS_PATH, "w") as f:
        json.dump(alerts, f, indent=2)

    print(f"Generated {len(registry)} registry entities -> {REGISTRY_PATH}")
    print(f"Generated {len(alerts)} alerts -> {ALERTS_PATH}")


if __name__ == "__main__":
    main()
