# Email Classification POC — TypeSafe Jev via OpenRouter

A small proof-of-concept that classifies a batch of sample emails into
**spam / not_spam / important** using TypeSafe's Jev decisioning model
(`typesafe/jev-1.13` on OpenRouter), then routes each to an action in code.

Unlike the sibling `code-review-poc/` (which fans out several Score/Noul
questions per item), this POC exercises the **Choice** primitive: one
mutually-exclusive pick among three labels per email, called concurrently across
a batch — the "classify at volume" pattern.

## Dataset

500 synthetic sample emails under `emails/<true_label>/*.txt` (~166 per
category), each a simple `From:` / `Subject:` header block followed by a blank
line and a body. The parent folder name is the ground-truth label, used only
for scoring — Jev never sees it.

The dataset is generated, not hand-written, by `generate_emails.py`: ~8
randomized templates per category (lottery scams, phishing invoices, crypto
pumps, security alerts, outage pages, coworker updates, receipts, newsletters,
etc.), each filled in with `Faker`-generated names/companies/amounts/dates so
every email is unique. Regenerate (or resize) the dataset with:

```bash
python generate_emails.py --total 500 --seed 42
```

This **wipes and rebuilds** `emails/`. `--seed` makes the dataset reproducible.

## How it decides

One Choice question per email:

```json
{
  "type": "choice",
  "instructions": "Classify this email into exactly one category based on its sender, subject, and body content.",
  "criteria": {
    "spam": "Unsolicited scam/commercial content...",
    "important": "Legitimate email that is time-sensitive or high-stakes...",
    "not_spam": "Legitimate email that is not urgent..."
  }
}
```

`state` is that email's `{from, subject, body}`. All calls run concurrently
(`ThreadPoolExecutor`, 300 workers) against a shared, connection-pooled
`requests.Session` (pool size 300) with automatic retries on transient errors
(429/500/502/503/504). Concurrency was stress-tested up to 3,000 emails: throughput
scales cleanly through 300 concurrent workers (3,000 emails in ~6.6s, zero
errors) with no further gain at 600, so 300 is the tuned default. A failure
that survives the retries is still caught and reported rather than aborting
the whole batch.

Code then applies a confidence gate before acting, per TypeSafe's
[confidence guidance](https://docs.typesafe.ai/confidence): if `confidence < 0.5`,
the action is `NEEDS_REVIEW` regardless of the predicted label; otherwise the
label maps directly to an action (`spam` → "Move to Spam folder", `important` →
"Flag + notify", `not_spam` → "Deliver to Inbox").

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
```

## Run

```bash
python classify.py              # progress + misclassifications + summary
python classify.py --verbose    # also print every single email's result
```

Prints progress every 50 completions, then by default only the misclassified
emails (to stay readable at 500 rows) followed by a summary: overall accuracy,
a 3×3 confusion matrix, and average confidence split by correct vs. incorrect
predictions — a quick way to see whether Jev's confidence is actually
well-calibrated on this dataset, rather than assuming it is.

A live run against the generated 500-email dataset (seed 42) classified all
500 in about 4 seconds (with connection pooling + retries) and got
**479/500 correct (96%)**. Nearly all misses came from a single template
(`notspam_hr_admin`, HR deadline reminders), consistently called `important`
instead of `not_spam` at 0.80-0.90 confidence — a systematic, not random,
judgment call on genuinely ambiguous "deadline"-flavored content, which is
exactly the kind of pattern a confusion matrix is meant to surface.

## Notes

- `jev_client.py` here is an exact copy of the adapter from `code-review-poc/`,
  verified live against OpenRouter's `POST /api/alpha/decisions` endpoint (the
  standard `chat/completions` endpoint rejects this model outright). Each POC
  keeps its own copy so the two remain independent, standalone demos.
- Most templates are written to be fairly unambiguous by design (obvious scam
  language for spam, obvious urgency markers for important), so high accuracy
  is expected; this is meant to demonstrate the pattern and how to read the
  confusion matrix, not serve as a rigorous spam-filter benchmark.
