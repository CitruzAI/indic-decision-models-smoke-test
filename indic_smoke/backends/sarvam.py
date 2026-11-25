"""Sarvam Prism via POST https://api.sarvam.ai/v2/systemone.

Docs: https://docs.sarvam.ai/api/token-factory/models/sarvam-prism
Auth: api-subscription-key: $SARVAM_API_KEY (Bearer also accepted).
"""

from __future__ import annotations

import time
from typing import Any

from indic_smoke.config import ModelSpec
from indic_smoke.http import env_key, request_json
from indic_smoke.prompts import LABELS, decisions_payload


def build_request(spec: ModelSpec, text: str) -> dict[str, Any]:
    return {"model": spec.model_id, **decisions_payload(text)}


def parse_answer(payload: dict[str, Any]) -> dict[str, Any]:
    answers = payload.get("answers") or {}
    answer = answers.get("sentiment") or {}
    probs = answer.get("probabilities") or {}
    pred = answer.get("choice")
    if pred not in LABELS and probs:
        pred = max(probs, key=probs.get)
    if probs and not all(label in probs for label in LABELS):
        return {"pred": pred, "probs": None, "error": "missing probabilities"}
    return {"pred": pred, "probs": {k: float(probs[k]) for k in LABELS} if probs else None}


def infer(spec: ModelSpec, text: str) -> dict[str, Any]:
    key = env_key(spec.auth_env)
    if not key:
        raise RuntimeError(f"{spec.auth_env} is not set in the current environment")
    t0 = time.perf_counter()
    status, payload = request_json(
        "POST",
        spec.endpoint,
        headers={"api-subscription-key": key, "Authorization": f"Bearer {key}"},
        body=build_request(spec, text),
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0
    cost = None  # Sarvam usage is in tokens / INR, not a USD usage.cost field we can trust
    usage = payload.get("usage")
    if status != 200:
        return {
            "pred": None,
            "probs": None,
            "latency_ms": latency_ms,
            "cost_usd": cost,
            "error": f"http {status}",
            "http_status": status,
            "usage": usage,
        }
    parsed = parse_answer(payload)
    parsed.update({"latency_ms": latency_ms, "cost_usd": cost, "http_status": status, "usage": usage})
    return parsed
