"""OpenRouter Decisions API: POST /api/alpha/decisions with state + questions.

Documented at https://openrouter.ai/docs/guides/features/decisions
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
    if answer.get("type") == "refusal":
        return {"pred": None, "probs": None, "error": "refusal", "raw_type": "refusal"}
    if answer.get("type") and answer.get("type") != "choice":
        return {
            "pred": None,
            "probs": None,
            "error": f"unexpected answer type {answer.get('type')!r}",
            "raw_type": answer.get("type"),
        }
    probs = answer.get("probabilities") or {}
    # Use the probability vector, not the vendor 'confidence' field (it may be rescaled).
    pred = answer.get("choice")
    if pred not in LABELS and probs:
        pred = max(probs, key=probs.get)
    missing = [label for label in LABELS if label not in probs]
    if missing and probs:
        return {"pred": pred, "probs": None, "error": f"missing probabilities for {missing}"}
    return {"pred": pred, "probs": {k: float(probs[k]) for k in LABELS} if probs else None}


def usage_cost_usd(payload: dict[str, Any]) -> float | None:
    usage = payload.get("usage") or {}
    if "cost" in usage and usage["cost"] is not None:
        return float(usage["cost"])
    return None


def infer(spec: ModelSpec, text: str) -> dict[str, Any]:
    key = env_key(spec.auth_env)
    if not key:
        raise RuntimeError(f"{spec.auth_env} is not set in the current environment")
    t0 = time.perf_counter()
    status, payload = request_json(
        "POST",
        spec.endpoint,
        headers={"Authorization": f"Bearer {key}"},
        body=build_request(spec, text),
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0
    if status != 200:
        return {
            "pred": None,
            "probs": None,
            "latency_ms": latency_ms,
            "cost_usd": usage_cost_usd(payload),
            "error": f"http {status}",
            "http_status": status,
        }
    parsed = parse_answer(payload)
    parsed["latency_ms"] = latency_ms
    parsed["cost_usd"] = usage_cost_usd(payload)
    parsed["http_status"] = status
    parsed["usage"] = payload.get("usage")
    return parsed
