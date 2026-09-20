# TypeSafe / Jev POCs

Six independent proof-of-concepts built on [TypeSafe](https://docs.typesafe.ai)'s
Jev decisioning model (`typesafe/jev-1.13`), called live through OpenRouter's
dedicated `POST /api/alpha/decisions` endpoint (the standard `chat/completions`
endpoint rejects this model — see any POC's `jev_client.py` for the confirmed
contract). Jev returns typed Choice/Noul/Score judgments instead of free text;
every POC here keeps the model to narrow, parallel per-item questions and lets
plain code own aggregation, thresholds, and the final decision.

Each POC is self-contained (own `jev_client.py`, `requirements.txt`, `.env`) so
they can be run independently:

| POC | Primitives used | What it demonstrates |
| --- | --- | --- |
| [`code-review-poc/`](code-review-poc/) | Score + Noul fan-out | Reviewing a code diff for security/correctness risk, with confidence-gated auto-approve/request-changes/needs-human-review verdicts. |
| [`email-classification-poc/`](email-classification-poc/) | Choice at volume | Classifying a batch of emails into spam/important/not_spam, with a confusion matrix and confidence-based routing. |
| [`feedback-mining-poc/`](feedback-mining-poc/) | Score + Noul + Choice, map-reduce | Mining product reviews for sentiment/topic/urgency, aggregated into a dashboard-style insights report (not just per-item labels). |
| [`guardrail-poc/`](guardrail-poc/) | Noul + Score, single-call guardrail | Screening inbound/outbound LLM chat messages for jailbreaks, harmful requests, sensitive-data exposure, and policy violations. |
| [`financial-crime-poc/`](financial-crime-poc/) | Score + Noul + Choice (entity resolution) | AML alert triage: hazard flags, fuzzy entity-name matching against a registry, composite risk/relevance/evidence scoring, and investigator routing. |

Every POC follows the same shape: a `generate_*.py` script builds a synthetic,
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
