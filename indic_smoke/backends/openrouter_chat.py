"""OpenRouter chat completions with structured output, and logprobs where supported.

Documented at https://openrouter.ai/docs/api-reference/chat-completion and
https://openrouter.ai/docs/guides/features/structured-outputs (json_schema).
Self-reported confidence in the JSON body is ignored.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

from indic_smoke.config import ModelSpec
from indic_smoke.http import env_key, request_json
from indic_smoke.prompts import LABELS, llm_messages, llm_response_format


def build_request(spec: ModelSpec, text: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": spec.model_id,
        "messages": llm_messages(text),
        "response_format": llm_response_format(),
        "max_tokens": (
            4096
            if (spec.reasoning or {}).get("mandatory")
            else 64
        ),
        "temperature": 0,
    }
    if spec.reasoning_effort:
        body["reasoning_effort"] = spec.reasoning_effort
        body["reasoning"] = {"effort": spec.reasoning_effort, "enabled": False}
    if spec.supports_logprobs:
        body["logprobs"] = True
        body["top_logprobs"] = 5
    return body


def _probs_from_logprobs(choice: dict[str, Any]) -> dict[str, float] | None:
    """If the first content token's top_logprobs cover both labels, softmax them.

    This is best-effort. Structured output may wrap the label in JSON punctuation,
    in which case we return None rather than inventing a distribution.
    """
    logprobs = choice.get("logprobs") or {}
    content = logprobs.get("content") or []
    if not content:
        return None
    # Search the first few tokens for a raw label piece.
    for step in content[:8]:
        raw = (step.get("token") or "").strip().strip('"')
        top = step.get("top_logprobs") or []
        found: dict[str, float] = {}
        for item in top:
            piece = (item.get("token") or "").strip().strip('"')
            if piece in LABELS and "logprob" in item:
                found[piece] = float(item["logprob"])
        if raw in LABELS and raw not in found and "logprob" in step:
            found[raw] = float(step["logprob"])
        if len(found) >= 1 and any(label in found for label in LABELS):
            # If only one label appeared, we cannot form a two-way distribution honestly.
            if not all(label in found for label in LABELS):
                return None
            mx = max(found.values())
            exps = {k: math.exp(v - mx) for k, v in found.items()}
            z = sum(exps.values())
            return {k: exps[k] / z for k in LABELS}
    return None


def parse_answer(payload: dict[str, Any], supports_logprobs: bool) -> dict[str, Any]:
    choices = payload.get("choices") or []
    if not choices:
        return {"pred": None, "probs": None, "error": "no choices"}
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    pred = None
    try:
        parsed = json.loads(content)
        pred = parsed.get("label")
    except (json.JSONDecodeError, AttributeError, TypeError):
        # Fall back to finding an exact label in the raw text, nothing fuzzier.
        stripped = content.strip().strip('"')
        if stripped in LABELS:
            pred = stripped
        else:
            return {"pred": None, "probs": None, "error": "unparseable content"}
    if pred not in LABELS:
        return {"pred": pred, "probs": None, "error": f"label not in enum: {pred!r}"}
    probs = _probs_from_logprobs(choice) if supports_logprobs else None
    return {"pred": pred, "probs": probs}


def usage_cost_usd(payload: dict[str, Any]) -> float | None:
    usage = payload.get("usage") or {}
    if "cost" in usage and usage["cost"] is not None:
        return float(usage["cost"])
    return None



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
        timeout=180.0,
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0
    if status != 200:
        return {
            "pred": None,
            "probs": None,
            "latency_ms": latency_ms,
            "cost_usd": usage_cost_usd(payload),
            "error": _http_error(status, payload),
            "http_status": status,
            "usage": payload.get("usage") if isinstance(payload, dict) else None,
            "model": payload.get("model") if isinstance(payload, dict) else None,
        }
    parsed = parse_answer(payload, spec.supports_logprobs)
    parsed["latency_ms"] = latency_ms
    parsed["cost_usd"] = usage_cost_usd(payload)
    parsed["http_status"] = status
    parsed["usage"] = payload.get("usage")
    parsed["model"] = payload.get("model")
    return parsed
