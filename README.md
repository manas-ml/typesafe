# TypeSafe / Jev POCs

Ten independent proof-of-concepts built on [TypeSafe](https://docs.typesafe.ai)'s
Jev decisioning model (`typesafe/jev-1.13`), called live through OpenRouter's
dedicated `POST /api/alpha/decisions` endpoint (the standard `chat/completions`
endpoint rejects this model — see any POC's `jev_client.py` for the confirmed
contract). Jev returns typed Choice/Noul/Score judgments instead of free text;
every POC here keeps the model to narrow, parallel per-item questions and lets
plain code own aggregation, thresholds, and the final decision. Seven of the
ten are single-pass, batch-map style (one `call_jev()` per item, code-owned
reduce) — `db-trends-poc` included, which adds persisting each judgment as a
database column so later trend queries never re-invoke Jev at all.
`word-guess-poc`, `twenty-questions-poc`, and `ai-shooter-poc` are the loop
exceptions — each runs Jev **in a code-owned loop**, one bounded judgment per
round, until the loop's task is complete (or, for `ai-shooter-poc`, on a
repeating cadence inside a live game loop rather than a turn-based one).

Each POC is self-contained (own `jev_client.py`, `requirements.txt`, `.env`) so
they can be run independently:

| POC | Primitives used | What it demonstrates |
| --- | --- | --- |
| [`code-review-poc/`](code-review-poc/) | Score + Noul fan-out | Reviewing a code diff for security/correctness risk, with confidence-gated auto-approve/request-changes/needs-human-review verdicts. |
| [`email-classification-poc/`](email-classification-poc/) | Choice at volume | Classifying a batch of emails into spam/important/not_spam, with a confusion matrix and confidence-based routing. |
| [`feedback-mining-poc/`](feedback-mining-poc/) | Score + Noul + Choice, map-reduce | Mining product reviews for sentiment/topic/urgency, aggregated into a dashboard-style insights report (not just per-item labels). |
| [`guardrail-poc/`](guardrail-poc/) | Noul + Score, single-call guardrail | Screening inbound/outbound LLM chat messages for jailbreaks, harmful requests, sensitive-data exposure, and policy violations. |
| [`financial-crime-poc/`](financial-crime-poc/) | Score + Noul + Choice (entity resolution) | AML alert triage: hazard flags, fuzzy entity-name matching against a registry, composite risk/relevance/evidence scoring, and investigator routing. |
| [`word-guess-poc/`](word-guess-poc/) | Choice, in a loop | A code-owned loop plays a Wordle-style word game to completion: code computes information-gain per round, Jev picks the likeliest real-word candidate, confidence-gated fallback to pure entropy. Has a CLI and a small web UI to watch it play live. |
| [`twenty-questions-poc/`](twenty-questions-poc/) | Choice + Noul, in a loop | You think of something; a code-owned loop asks yes/no questions and guesses it, live in a browser chat UI. Belief updates run over a precomputed entity/question matrix (exact math); Jev picks which question to ask next and judges when to commit to a guess, each confidence-gated. |
| [`ai-shooter-poc/`](ai-shooter-poc/) | Choice + Score, in a real-time game loop | A live top-down browser shooter: code runs physics/collision every frame, while each enemy asks Jev for its next tactic (advance/retreat/strafe/hold/flee) and an aggression level roughly every 2 seconds, confidence-gated to a deterministic fallback rule. |
| [`db-trends-poc/`](db-trends-poc/) | Choice + Score + Noul, enrich-once-then-SQL | A synthetic 100k-row SQLite ticket table with planted trends. Jev enriches a stratified per-month sample once, caching judgments as columns; every trend query after that is pure SQL. Recovers a shipping-delay trend structurally invisible to the raw category tag. |

The first six POCs follow the same shape: a `generate_*.py` script builds a synthetic,
`Faker`-backed, reproducible (`--seed`) dataset; a second script runs one Jev
call per item (several parallel questions each) concurrently via a shared,
connection-pooled, auto-retrying `requests.Session`; and a code-owned policy
turns the raw typed answers into a verdict/report. See each POC's own README
for its exact questions, decision policy, and a live example run.

## Setup (per POC)

```bash
cd <poc-directory>
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
python generate_*.py   # build the dataset (script name varies per POC)
python <main_script>.py
```
