# Code Review POC — TypeSafe Jev via OpenRouter

A small proof-of-concept that triages code diffs using TypeSafe's Jev decisioning
model (`typesafe/jev-1.13` on OpenRouter). Instead of asking an LLM to write a free-text
review, this asks Jev four narrow, typed questions per diff (two `Score`, two `Noul`,
per [TypeSafe's primitives](https://docs.typesafe.ai/primitives)) and lets ordinary
Python code turn those typed answers into a verdict.

## How it decides

One fan-out call per diff asks:

- `security_risk` (Score, 0–3): hardcoded secrets, injection, missing auth, etc.
- `correctness_risk` (Score, 0–3): likelihood the change breaks behavior.
- `breaking_change` (Noul): does this break a public/external contract?
- `needs_tests` (Noul): non-trivial logic added with no test changes?

Code then applies a fixed policy (`decide()` in `review.py`):

1. If confidence on either Score question is below 0.5 → `NEEDS_HUMAN_REVIEW`
   (per TypeSafe's [confidence guidance](https://docs.typesafe.ai/confidence),
   low confidence should route to a person, not be trusted as a mid-range score).
2. Else if `security_risk` or `correctness_risk` is 2 or higher → `REQUEST_CHANGES`.
3. Else → `AUTO_APPROVE`.
4. Independently, `breaking_change` / `needs_tests` above 0.6 add advisory flags to
   the report without changing the verdict on their own.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
```

## Run

```bash
python review.py fixtures/risky_change.diff
python review.py --all   # runs every fixture in fixtures/
```

Three fixtures are included, expected to land in different tiers:

- `fixtures/safe_change.diff` — comment + formatting only → `AUTO_APPROVE`.
- `fixtures/moderate_change.diff` — new branching logic, no tests touched →
  `REQUEST_CHANGES` or at least a `needs_tests` flag.
- `fixtures/risky_change.diff` — hardcoded API key, string-concatenated SQL, and a
  removed auth check → `REQUEST_CHANGES` with a high `security_risk` score.

Since Jev's scoring is model-driven, exact scores may vary between runs — the point
of the demo is that the three fixtures should clearly separate into different
verdicts, not that any single number is fixed.

## The OpenRouter contract (confirmed live)

TypeSafe's documentation (docs.typesafe.ai) fully specifies its **native** API
(`POST https://api.typesafe.ai/v1/systemone`) but never mentions OpenRouter.
The standard `POST https://openrouter.ai/api/v1/chat/completions` endpoint
**rejects** `typesafe/jev-1.13` outright:

> `typesafe/jev-1.13 is a decisions model and cannot be used with the
> chat/completions endpoint. Use the /api/alpha/decisions endpoint instead.`

Jev is reached through a dedicated OpenRouter endpoint instead,
`POST https://openrouter.ai/api/alpha/decisions`, which mirrors TypeSafe's native
contract exactly — same `{"model", "state", "questions"}` request body, and a
response of `{"model", "answers", "usage", "id", "provider"}`. `jev_client.py`
implements exactly that (verified against a live run of this POC).
