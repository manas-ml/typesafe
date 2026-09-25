# DB Trends POC — Jev over a large local SQLite table

Answers a concrete follow-up to `research-trends-poc`: what does "run Jev
analysis over a large database table" actually look like, mechanically? This
POC builds a synthetic, 100,000-row support-ticket table in local SQLite and
demonstrates the pattern end to end: **enrich a sample of rows with Jev once,
cache the judgment as columns on the row, and do every actual trend query
afterward in pure SQL** — no re-inference, no matter how large the table is.

## The table

`generate_tickets.py` builds `data/tickets.db`, a `tickets` table with three
deliberately planted patterns to verify against (same "synthetic data with
planted patterns" convention as every other POC in this repo except
`research-trends-poc`, which uses real data instead):

1. **`billing` complaints rise over the last 3 months** — the raw
   `product_area` tag is accurate here, so plain SQL on the exact column
   already shows this trend on its own.
2. **Shipping/delivery complaints have no dedicated raw tag** (a realistic
   legacy-schema gap) — they're always logged as `other`, and they spike hard
   in the very last month. Raw-tag SQL structurally cannot separate this from
   everything else dumped into `other`.
3. **Enterprise-tier tickets increasingly contain churn-risk language**
   ("considering canceling," "evaluating alternatives") in the last 2 months
   — there's no exact column for this at all; it only exists as free text.

Patterns 2 and 3 are the actual point of the POC: they're real signals sitting
in a real (if synthetic) 100k-row table that **no SQL query over the existing
schema could ever surface**, because the schema has nowhere to put them.

## The pattern: enrich once, cache it, then SQL forever

- **`enrich.py`** — asks Jev to re-read each ticket's actual text and answer
  four questions (Choice `category`, Score `sentiment`, Noul `urgent`, Noul
  `churn_risk`), then writes the answers back as columns on that same row
  (`jev_category`, `jev_sentiment`, ...) plus a `jev_analyzed_at` timestamp.
  Every run only touches rows still missing `jev_analyzed_at` — enrichment
  accumulates across runs instead of re-paying for rows already done.
- **`report.py`** — pure SQL, zero Jev calls. Section 1 runs over the full
  table using only the exact columns `generate_tickets.py` wrote. Section 2
  runs over `WHERE jev_analyzed_at IS NOT NULL` — the enriched subset —
  using only the cached Jev columns. Once a row is enriched, this script
  never touches Jev again for it; querying it is as cheap as any other SQL
  query, at any table size.

## Why sampling, not "enrich all 100k rows"

`enrich.py` defaults to a **stratified sample: up to 50 not-yet-analyzed rows
per calendar month** (not a flat random sample of the whole table), so every
month gets comparable coverage for a fair trend comparison even though raw
monthly volume differs — the same reasoning as the stratified sampling in
`research-trends-poc`. `--per-month N` takes a bigger sample; `--all` enriches
every remaining row (expensive at 100k scale: that's ~100k live Jev calls,
not a couple hundred — only do this if you actually want to pay for full
coverage, not to see the pattern demonstrated).

## Run

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY

python generate_tickets.py              # build the 100k-row table (instant, no Jev calls)
python enrich.py                        # enrich ~50 rows/month (~600 Jev calls total)
python report.py                        # section 1 (full table, SQL only) + section 2 (enriched subset)

python enrich.py --per-month 150        # optional: enrich more for a stronger signal, then re-run report.py
```

## Notes

- `jev_client.py` is the same shared, connection-pooled, auto-retrying
  adapter used across every POC in this repo.
- `data/tickets.db` is regenerated (dropped and rebuilt) by
  `generate_tickets.py` — re-run it to reset the table, including clearing
  all enrichment.
- No web UI here (unlike `word-guess-poc`, `twenty-questions-poc`,
  `ai-shooter-poc`) — this one is about the database/SQL pattern, not an
  interactive demo, so a CLI matches `financial-crime-poc`/
  `research-trends-poc`'s convention instead.
