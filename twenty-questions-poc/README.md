# 20 Questions vs Jev — Jev in a code-owned loop

A second loop-based POC (alongside `word-guess-poc`): you think of something
from a ~110-item candidate pool (animals, everyday objects, real people,
fictional characters, places), and a code-owned game loop tries to guess it
by asking yes/no questions, one at a time, in a browser chat UI.

Unlike `word-guess-poc` (where Jev only supplies a soft "commonness" prior on
top of an exactly-computable feedback rule), there's no exact ground truth
here — narrowing down "what is the person thinking of" is a genuinely fuzzy
problem from start to finish. Jev makes two live, per-round judgment calls
that a lookup table alone can't:

1. **Which question to ask next** — code shortlists the 5 questions with the
   highest expected information gain (given the current belief), Jev picks
   the best one to actually ask.
2. **When to stop asking and guess, and what to guess** — Jev judges whether
   the current belief is confident enough to commit, and if so, which
   leading candidate is right.

Both are confidence-gated: a low-confidence Jev answer falls back to the
plain code-computed choice (highest information gain / highest belief)
instead of acting on a shaky judgment — same pattern as `word-guess-poc`.

## Why a precomputed matrix

Nothing here has an exact feedback rule the way Wordle's green/yellow/gray
does. So the *belief-update* math (which has to run after every human
answer) is made exact instead: `generate_matrix.py` asks Jev, once per
entity, to answer all ~30 yes/no questions from `data/questions.py` as
parallel Noul judgments, and caches the resulting probabilities in
`data/matrix.json`. During an actual game, updating the belief distribution
and ranking candidate questions by information gain is then pure arithmetic
over that cached matrix — no Jev call needed for it, and it can't drift
mid-game. The two Jev calls per round are reserved for the judgments the
matrix genuinely can't make on its own.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY

python generate_matrix.py       # one-time: build data/matrix.json (~110 Jev calls)
python app.py                   # start the web UI
# open http://localhost:5051
```

Think of something from the categories above, then click through. The right
panel shows Jev's current top guess and round count; each chat bubble is
tagged with Jev's confidence and whether the fallback kicked in.

## Notes

- `jev_client.py` is the same shared, connection-pooled, auto-retrying
  adapter used across every POC in this repo.
- Game state lives server-side in an in-memory dict keyed by a `game_id`
  (fine for this single-process demo; not meant to survive a restart).
- The belief update floors each factor at 0.02 (`MIN_UPDATE_FACTOR` in
  `game.py`) so one noisy precomputed matrix answer can't permanently zero
  out the true candidate.
- Capped at 15 questions and 3 guess attempts (`MAX_ROUNDS` /
  `MAX_GUESS_ATTEMPTS` in `game.py`) so a bad run ends instead of looping
  forever.
- Runs on port 5051 by default — 5000 is claimed by macOS's AirPlay
  Receiver, 5050 is used by `word-guess-poc`.
