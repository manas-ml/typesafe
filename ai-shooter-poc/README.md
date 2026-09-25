# AI Shooter — Jev-controlled Enemies

A third loop-based POC (alongside `word-guess-poc` and `twenty-questions-poc`),
and a different loop shape than either: a real top-down shooter, running a
60fps physics/render loop entirely in the browser, where **enemy tactics are
decided by Jev periodically** — roughly every ~2 seconds per enemy, not every
frame.

## Why this loop cadence

Jev calls are a network round-trip; they can't drive a 60fps per-frame
decision the way a raycasting Doom-style engine would need. So the split is:

- **Code (every frame, exact):** player/enemy movement and physics,
  projectile motion, collision, damage, health, win/loss detection. This
  never waits on a network call.
- **Jev (every ~1.6–2.4s per enemy, jittered so multiple enemies don't all
  call at once):** given the enemy's own health, the player's health, and
  the distance between them, one **Choice** of tactical action
  (`advance` / `retreat` / `strafe` / `hold_and_fire` / `flee`) plus one
  **Score** for how aggressively to play it (scales movement speed and fire
  rate for that stretch). Between calls, the enemy just keeps executing its
  last decision — the game never freezes waiting on Jev.
- **Confidence-gated fallback:** if Jev's `next_action` choice is invalid or
  its confidence is below 0.3, code falls back to a simple deterministic
  rule (flee if low health, advance if far, retreat if too close, otherwise
  hold and fire) — same pattern used in `word-guess-poc` and
  `twenty-questions-poc`.
- **Event-triggered re-decision:** an enemy also forces an immediate
  re-decision (instead of waiting for its next scheduled interval) the first
  time its health drops below 30%, so a badly-hurt enemy doesn't keep
  advancing on a stale decision.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY

python app.py
# open http://localhost:5052
```

WASD/arrow keys to move, hold the mouse button to fire toward the cursor.
The side panel shows each enemy's current action, Jev's confidence, and
whether the fallback kicked in — so the AI's reasoning stays visible instead
of hidden behind the game.

## Notes

- `jev_client.py` is the same shared, connection-pooled, auto-retrying
  adapter used across every POC in this repo.
- No dataset or precompute step here (unlike `twenty-questions-poc`) — every
  decision is made live from the current, dynamic game state (health,
  distance), which can't be precomputed ahead of time.
- Single open arena, two enemies, no cover/obstacles — kept intentionally
  small in scope; the point is the Jev decision loop, not a full game engine.
- Runs on port 5052 — 5000 is claimed by macOS's AirPlay Receiver, 5050/5051
  are used by the other two loop POCs.
