# Word Guesser POC — Jev in a code-owned loop

A proof-of-concept that runs TypeSafe's Jev model **in a loop** rather than
as a single per-item call: a code-owned loop plays a Wordle-style hidden-word
game to completion, calling Jev once per round for the one genuinely fuzzy
decision in an otherwise deterministic game.

Every other POC in this repo (`code-review-poc`, `email-classification-poc`,
`feedback-mining-poc`, `financial-crime-poc`, `guardrail-poc`) is single-pass:
one `call_jev()` per item. This one demonstrates TypeSafe's documented
guidance for iterative use: **code owns the loop and all exact logic; Jev
supplies one narrow, bounded judgment per round**, the same shape as
TypeSafe's own `autoresearch_feature_discovery` cookbook (propose → ask Jev →
evaluate → decide whether to continue).

## The game

A secret 5-letter word is picked from `data/words.py`. Each round, the
player guesses a word and gets green/yellow/gray feedback (exact letter
match / letter present elsewhere / letter absent), Wordle-style. The game
ends when the guess is correct or after 6 guesses.

## What stays in code vs. what Jev decides

- **Code (`wordle.py`, exact rules/calculations):** feedback scoring,
  candidate-set filtering after each guess, and information-gain (Shannon
  entropy) for every remaining candidate — a standard Wordle-solver
  technique. The loop itself, win/loss detection, and all reporting also
  stay in code (`solver.py`).
- **Jev (the one fuzzy judgment per round):** the top-entropy words are all
  *statistically* the best next guesses, but entropy alone can't tell "COYPU"
  (an obscure but valid word) from "HOUSE" (a common one) — which matters
  because the secret is drawn from real, commonly-used words. So each round,
  code shortlists the top 8 highest-entropy candidates and asks Jev a single
  **Choice** question: given these information-maximizing candidates, which
  one is most likely to actually be a common answer word? If Jev's
  `confidence` is below `0.35`, the round falls back to the plain
  top-entropy candidate instead — Jev's pick is used opportunistically, the
  game never depends on it to keep playing (confidence-gated routing, same
  pattern used for human handoff in `financial-crime-poc`).

## Run: CLI (batch stats)

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY

python solver.py --games 10 --verbose    # see every round's transcript
python solver.py --games 50              # aggregate win rate / guess histogram
python solver.py --games 50 --baseline   # same, but skip Jev entirely (ablation)
```

Compare the `--baseline` run against the normal run to see whether Jev's
semantic pick actually improves average guesses over pure entropy, or just
adds latency — the POC is set up to answer that, not just to run.

## Run: web UI (watch the loop live)

```bash
python app.py
# open http://localhost:5050
```

Click **New Game** to play one game end-to-end; the board animates one round
at a time as the loop decides it, with a side panel showing the candidates
Jev considered, its pick and confidence, and whether the fallback kicked in.
The **baseline** checkbox reruns the same loop with Jev skipped, for a direct
side-by-side comparison.

## Notes

- `jev_client.py` is the same shared, connection-pooled, auto-retrying
  adapter used across every POC in this repo, hitting OpenRouter's
  `POST /api/alpha/decisions` endpoint with `typesafe/jev-1.13`.
- The guess pool is restricted to still-possible candidates each round
  (rather than the full guess dictionary some Wordle solvers use for the
  opening move) — a deliberate simplification to keep the loop and the Jev
  question small; it costs a little optimality, not correctness.
- `data/words.py` is a hardcoded ~530-word list of common 5-letter English
  words (answer pool and guess pool are the same list here), kept
  dependency-free rather than pulling an external word-list package.
