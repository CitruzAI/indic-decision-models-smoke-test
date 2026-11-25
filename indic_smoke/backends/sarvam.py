"""Sarvam Prism via POST https://api.sarvam.ai/v2/systemone.

Docs: https://docs.sarvam.ai/api/token-factory/models/sarvam-prism
Auth: api-subscription-key: $SARVAM_API_KEY (Bearer also accepted).
Official list price: ₹4 / 1M input tokens, ₹0 output (every plan).
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from indic_smoke.config import ModelSpec
from indic_smoke.http import env_key, request_json
from indic_smoke.task import SENTIMENT, TaskSpec

INR_PER_1M_INPUT = Decimal("4")


def build_request(spec: ModelSpec, text: str, task: TaskSpec = SENTIMENT) -> dict[str, Any]:
    return {"model": spec.model_id, **task.decisions_payload(text)}


def parse_answer(payload: dict[str, Any], task: TaskSpec = SENTIMENT) -> dict[str, Any]:
    answers = payload.get("answers") or {}
    answer = answers.get(task.question_name) or {}
    labels = task.labels
    if answer.get("type") == "refusal":
        return {"pred": None, "probs": None, "error": "refusal", "raw_type": "refusal"}
    probs = answer.get("probabilities") or {}
    pred = answer.get("choice")
    if pred not in labels and probs:
        pred = max(probs, key=probs.get)
    if probs and not all(label in probs for label in labels):
        return {"pred": pred, "probs": None, "error": "missing probabilities"}
    return {"pred": pred, "probs": {k: float(probs[k]) for k in labels} if probs else None}


def _http_error(status: int, payload: dict[str, Any] | None) -> str:
    detail = ""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            parts = [str(err.get(k)) for k in ("code", "type", "message") if err.get(k)]
            detail = " ".join(parts)
        elif isinstance(err, str):
            detail = err[:500]
        elif payload.get("message"):
            detail = str(payload["message"])[:500]
    return f"http {status}" + (f": {detail}" if detail else "")


def usage_prompt_tokens(usage: dict[str, Any] | None) -> int | None:
    if not usage:
        return None
    for key in ("prompt_tokens", "input_tokens", "total_tokens"):
        if usage.get(key) is not None:
            return int(usage[key])
    return None


def cost_inr_from_usage(usage: dict[str, Any] | None) -> tuple[float | None, str]:
    tokens = usage_prompt_tokens(usage)
    if tokens is None:
        return None, "missing"
    cost = (INR_PER_1M_INPUT / Decimal("1000000")) * Decimal(tokens)
    return float(cost), "usage_tokens_x_listed_inr_4_per_1m"


def infer(spec: ModelSpec, text: str, task: TaskSpec = SENTIMENT) -> dict[str, Any]:
    key = env_key(spec.auth_env)
    if not key:
        raise RuntimeError(f"{spec.auth_env} is not set in the current environment")
    t0 = time.perf_counter()
    status, payload = request_json(
        "POST",
        spec.endpoint,
        headers={"api-subscription-key": key, "Authorization": f"Bearer {key}"},
        body=build_request(spec, text, task),
        timeout=120.0,
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0
    usage = payload.get("usage") if isinstance(payload, dict) else None
    cost_inr, cost_source = cost_inr_from_usage(usage if isinstance(usage, dict) else None)
    base = {
        "latency_ms": latency_ms,
        "cost_usd": None,
        "cost_inr": cost_inr,
        "cost_source": cost_source,
        "http_status": status,
        "usage": usage,
        "model": payload.get("model") if isinstance(payload, dict) else None,
    }
    if status != 200:
        base.update(
            {
                "pred": None,
                "probs": None,
                "error": _http_error(status, payload if isinstance(payload, dict) else None),
            }
        )
        return base
    parsed = parse_answer(payload, task)
    parsed.update(base)
    return parsed
