"""Deterministic Wordle-style game mechanics: feedback scoring, candidate
filtering, and information-gain (entropy) computation.

These are exact rules and calculations, so they stay in code -- Jev is never
asked to compute a feedback pattern or an entropy score, only to make the
one fuzzy judgment call (see solver.py: which information-maximizing
candidate is most likely to be the real answer).
"""

from collections import Counter
from math import log2


def score_guess(guess: str, secret: str) -> str:
    """Return a 5-character feedback pattern: 'G' green, 'Y' yellow, 'X' gray."""
    guess = guess.lower()
    secret = secret.lower()
    feedback = ["X"] * 5
    remaining = list(secret)

    for i in range(5):
        if guess[i] == secret[i]:
            feedback[i] = "G"
            remaining[i] = None

    for i in range(5):
        if feedback[i] == "G":
            continue
        if guess[i] in remaining:
            feedback[i] = "Y"
            remaining[remaining.index(guess[i])] = None

    return "".join(feedback)


def filter_candidates(candidates: list, guess: str, feedback: str) -> list:
    """Keep only candidates that would produce this exact feedback for this guess."""
    return [c for c in candidates if score_guess(guess, c) == feedback]


def entropy(candidate: str, remaining_candidates: list) -> float:
    """Expected information gain (bits) from guessing `candidate` against the
    current candidate set -- the Shannon entropy of the feedback-pattern
    partition it induces.
    """
    total = len(remaining_candidates)
    if total <= 1:
        return 0.0
    pattern_counts = Counter(score_guess(candidate, c) for c in remaining_candidates)
    return -sum(
        (count / total) * log2(count / total) for count in pattern_counts.values()
    )
