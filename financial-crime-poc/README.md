# Financial Crime Alert Triage POC — TypeSafe Jev via OpenRouter

A proof-of-concept AML (anti-money-laundering) alert triage pipeline built on
TypeSafe's Jev model. Per alert it: flags suspicious characteristics,
resolves a messy customer name against a small entity registry, scores
risk/relevance/evidence quality, and combines all of that into a
code-owned prioritization and routing decision.

This is the broadest POC in this project — it combines every pattern used
across the other four: Noul hazard flags (`guardrail-poc`-style), Score-based
composite prioritization (`feedback-mining-poc`-style), a new use of
**Choice for entity resolution** (picking which known registry entity a
messy name variant refers to, or `no_match`), and confidence-gated routing
to a human (used throughout).

**Content note**: alert narratives are synthetic, abstract descriptions of
transaction *patterns* for classifier testing — the same kind of fixture used
in real AML software demos/training data. No real entities, no real PII (all
`Faker`-generated), no operational guidance on evading detection.

## Dataset

`data/entity_registry.json` — ~15 synthetic customers/businesses, each with a
canonical name and 1-2 alias variants (nickname, name change, or typo).

`data/alerts.json` — ~150 alerts, each referencing one registry entity
through a `mentioned_name` that is:
- **exact** (40%) — the canonical name, easy match.
- **alias** (30%) — a nickname/typo variant, harder match.
- **ambiguous** (30%) — deliberately blended with a different registry
  entity's name fragment, genuinely confusable between two real candidates.

Each alert also carries a narrative from one of 8 scenario templates spanning
genuine risk (structuring, high-risk-jurisdiction wires, shell-company
mismatches, rapid layering) and surface-pattern-only false positives
(payroll deposits, disclosed business growth, family transfers, a benign
gap in documentation) — so the model has to read substance, not just
pattern-match on transaction shape.

```bash
python generate_alerts.py --entities 15 --alerts 150 --seed 42
```

## How it triages (map step)

One call per alert, seven parallel questions over `state = {
transaction_narrative, kyc_snippet, alert_history_note, mentioned_name,
candidates }`:

- `structuring_indicator`, `high_risk_jurisdiction`, `identity_documentation_gap`
  (**Noul** each).
- `unusual_activity` (**Score**, 4 levels), `evidence_quality` (**Score**, 3
  levels), `alert_relevance` (**Score**, 3 levels).
- `entity_match` (**Choice**: one criterion per candidate entity, built from
  its registry name/aliases, plus `no_match`).

All alerts triage concurrently (`ThreadPoolExecutor`, 40 workers, progress
every 50) against the shared, connection-pooled, auto-retrying
`requests.Session` (see `jev_client.py`); a per-alert failure is caught and
reported rather than aborting the batch.

## Disposition (code-owned, not the model)

1. `entity_match` confidence `< 0.5` → **ROUTE_TO_INVESTIGATOR** — you can't
   act on a case without confidently knowing who it's about, regardless of
   risk score.
2. Either risk-score's confidence `< 0.5` → **ROUTE_TO_INVESTIGATOR**
   (ambiguous risk read), per TypeSafe's
   [confidence guidance](https://docs.typesafe.ai/confidence).
3. Otherwise, a composite `priority_score` = `unusual_activity` +
   `alert_relevance` + `evidence_quality` + a `+2` bonus if any hazard Noul
   is `> 0.6`:
   - `priority_score >= 5` → **AUTO_ESCALATE**.
   - `priority_score <= 2` and no hazard flags tripped → **AUTO_CLOSE**.
   - otherwise → **STANDARD_QUEUE**.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
```

## Run

```bash
python generate_alerts.py          # build the registry + alert dataset
python triage_alerts.py            # report + top escalations + investigator queue
python triage_alerts.py --verbose  # print every alert's disposition + full lists
```

Prints disposition counts, entity-match accuracy overall and broken down by
difficulty tier (exact/alias/ambiguous — accuracy should drop and
investigator routing should rise as difficulty increases), a priority-ranked
`AUTO_ESCALATE` list, and the `ROUTE_TO_INVESTIGATOR` queue with each case's
reason (identity ambiguous vs. ambiguous risk read).

A well-behaved run should show: high accuracy and few investigator routes on
`exact`-difficulty alerts, more investigator routes as difficulty rises to
`ambiguous`; and `AUTO_ESCALATE` dominated by the genuinely risky templates
(structuring, high-risk-jurisdiction, shell-company, rapid-movement) rather
than the surface-pattern-only false-positive templates.

## Notes

- `jev_client.py` is the same shared, connection-pooled, auto-retrying
  adapter used across every POC in this repo, hitting OpenRouter's
  `POST /api/alpha/decisions` endpoint.
- `true_entity_id` and `difficulty` are generation ground truth kept only for
  your own verification (the accuracy breakdown above) — never sent to Jev.
