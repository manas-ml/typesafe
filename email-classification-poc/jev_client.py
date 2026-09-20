"""
Adapter for calling TypeSafe's Jev decisioning model through OpenRouter.

TypeSafe's native API (docs.typesafe.ai) is:

    POST https://api.typesafe.ai/v1/systemone
    {"state": ..., "model": "jev-latest", "questions": {...}}
    -> {"answers": {...}, "usage": {...}}

OpenRouter exposes the same contract for Jev through a dedicated endpoint
(NOT the standard chat/completions endpoint -- that returns a 400 telling you
so): POST https://openrouter.ai/api/alpha/decisions, with the same
{"model", "state", "questions"} body, verified live to return
{"model", "answers", "usage", "id", "provider"}.

Uses a shared, connection-pooled Session with automatic retries so that
concurrent batch runs (see classify.py / mine_feedback.py) don't pay a fresh
TCP+TLS handshake per call and self-heal from transient errors (a live batch
run hit a one-off 504 that a retry would have absorbed) instead of surfacing
them as item failures.
"""

import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OPENROUTER_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"

POOL_SIZE = 300

_retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST"],
)
_adapter = HTTPAdapter(
    pool_connections=POOL_SIZE, pool_maxsize=POOL_SIZE, max_retries=_retry
)
_session = requests.Session()
_session.mount("https://", _adapter)


def call_jev(state: dict, questions: dict) -> dict:
    """Send one System One-style request to Jev via OpenRouter.

    Returns a dict mapping question id -> answer dict (e.g.
    {"type": "score", "score": 1.4, "confidence": 0.8, ...} or
    {"type": "noul", "noul": 0.92}), matching TypeSafe's documented answer
    shapes for Choice/Noul/Score.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in."
        )

    response = _session.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": MODEL, "state": state, "questions": questions},
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"OpenRouter request failed: {response.status_code}\n{response.text}"
        )

    body = response.json()

    try:
        return body["answers"]
    except KeyError as exc:
        raise RuntimeError(
            f"OpenRouter decisions response had no 'answers' key: {body}"
        ) from exc
