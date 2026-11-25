"""Offline cost estimate from tokenized prompts and snapshot prices. No network."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from indic_smoke.config import ModelSpec, registry
from indic_smoke.task import SENTIMENT, TaskSpec
from indic_smoke.tokenize_approx import (
    ENCODING_NAME,
    assumed_structured_output_text,
    count_tokens,
    token_report,
)

MONEY = Decimal("0.00000001")  # 1e-8 USD


def money(value: Decimal) -> str:
    q = value.quantize(MONEY, rounding=ROUND_HALF_UP)
    return format(q, "f")


def load_reviews(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def iter_texts(reviews: Iterable[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(id, lang, text) for the 240 evaluations."""
    out = []
    for row in reviews:
        for lang, field in (("en", "text_en"), ("hi", "text_hi"), ("ta", "text_ta")):
            out.append((row["id"], lang, row[field]))
    return out


def estimate_model(spec: ModelSpec, texts: list[tuple[str, str, str]], task: TaskSpec = SENTIMENT) -> dict[str, Any]:
    n = len(texts)
    per_lang_prompt = defaultdict(int)
    total_prompt = 0
    assumed_out = count_tokens(assumed_structured_output_text(task))
    for _id, lang, text in texts:
        report = token_report(text, task)
        if spec.family == "decisions":
            tokens = report["decisions_prompt_tokens"]
        else:
            tokens = report["chat_prompt_tokens"]
        per_lang_prompt[lang] += tokens
        total_prompt += tokens

    result: dict[str, Any] = {
        "key": spec.key,
        "display_name": spec.display_name,
        "model_id": spec.model_id,
        "provider": spec.provider,
        "family": spec.family,
        "n_requests": n,
        "tokenizer": ENCODING_NAME,
        "tokenizer_note": (
            "tiktoken o200k_base is an approximation for all models. "
            "Decision-model counts are tokens of the compact JSON payload "
            "(state + questions). Chat counts include the system prompt, the "
            "review, and the json_schema. This is not the provider's billed tokenizer."
        ),
        "prompt_tokens_total": total_prompt,
        "prompt_tokens_by_language": dict(per_lang_prompt),
        "price_found": spec.price_found,
        "price_source": spec.price_source,
        "runnable_id_confirmed": spec.runnable_id_confirmed,
        "prompt_usd_per_1m": None if spec.prompt_usd_per_1m is None else money(spec.prompt_usd_per_1m),
        "completion_usd_per_1m": None if spec.completion_usd_per_1m is None else money(spec.completion_usd_per_1m),
        "request_usd": money(spec.request_usd),
        "notes": list(spec.notes),
    }

    if not spec.price_found or spec.prompt_usd_per_token is None:
        result["prompt_usd"] = None
        result["completion_usd"] = None
        result["request_fees_usd"] = None
        result["total_usd"] = None
        result["estimate_complete"] = False
        result["incomplete_reason"] = (
            "No official USD list price, or the OpenRouter id has no priced endpoint."
        )
        if spec.key == "sarvam":
            # Official INR: ₹4 / 1M input. Report INR only, do not invent an FX rate.
            inr_per_token = Decimal("4") / Decimal("1000000")
            result["prompt_inr"] = money(inr_per_token * total_prompt)
            result["prompt_inr_rate"] = "₹4 per 1M input tokens (official, every plan)"
            result["completion_inr"] = "0"
        return result

    prompt_usd = spec.prompt_usd_per_token * Decimal(total_prompt)
    request_fees = spec.request_usd * Decimal(n)
    completion_usd = Decimal("0")
    estimate_complete = True
    incomplete_reason = None
    assumed_completion_tokens = 0

    if spec.family == "chat":
        reasoning = spec.reasoning or {}
        mandatory = bool(reasoning.get("mandatory"))
        if mandatory:
            estimate_complete = False
            incomplete_reason = (
                "Reasoning is mandatory on this model. Completion and reasoning "
                "tokens were not guessed, so only the prompt cost is included."
            )
        else:
            assumed_completion_tokens = assumed_out * n
            completion_usd = (spec.completion_usd_per_token or Decimal("0")) * Decimal(
                assumed_completion_tokens
            )
            result["assumed_completion_tokens_total"] = assumed_completion_tokens
            result["assumed_completion_tokens_each"] = assumed_out
            result["assumed_completion_note"] = (
                f"Assumes reasoning_effort=none and a structured body of "
                f"{assumed_out} {ENCODING_NAME} tokens "
                f"({assumed_structured_output_text(task)!r}) per request."
            )

    total = prompt_usd + completion_usd + request_fees
    result.update(
        {
            "prompt_usd": money(prompt_usd),
            "completion_usd": money(completion_usd),
            "request_fees_usd": money(request_fees),
            "total_usd": money(total),
            "estimate_complete": estimate_complete,
            "incomplete_reason": incomplete_reason,
        }
    )
    return result


def estimate_all(reviews: list[dict[str, Any]], task: TaskSpec = SENTIMENT) -> dict[str, Any]:
    texts = iter_texts(reviews)
    if len(texts) != 240:
        raise RuntimeError(f"expected 240 texts, found {len(texts)}")
    specs = registry()
    models = [estimate_model(spec, texts, task) for spec in specs]
    priced = [m for m in models if m["total_usd"] is not None]
    complete = [m for m in priced if m["estimate_complete"]]
    incomplete = [m for m in priced if not m["estimate_complete"]]
    missing = [m for m in models if m["total_usd"] is None]
    total_complete = sum((Decimal(m["total_usd"]) for m in complete), Decimal("0"))
    total_priced_prompt = sum((Decimal(m["prompt_usd"]) for m in priced), Decimal("0"))
    # A "headline" total: complete estimates plus the prompt-only part of incomplete ones.
    # Labeled clearly; not a promise of the billed amount.
    headline = total_complete + sum((Decimal(m["prompt_usd"]) for m in incomplete), Decimal("0"))
    return {
        "n_items": len(reviews),
        "n_texts": len(texts),
        "languages": ["en", "hi", "ta"],
        "tokenizer": ENCODING_NAME,
        "label_counts": dict(Counter(r["label"] for r in reviews)),
        "models": models,
        "totals": {
            "usd_complete_estimates_only": money(total_complete),
            "usd_prompt_only_sum_of_priced_models": money(total_priced_prompt),
            "usd_headline_complete_plus_prompt_of_incomplete": money(headline),
            "headline_includes": [m["model_id"] for m in complete + incomplete],
            "excluded_from_usd_total": [m["model_id"] for m in missing],
            "note": (
                "The headline total is the sum of complete USD estimates plus the "
                "prompt-only cost of priced models whose reasoning tokens could not "
                "be estimated. It excludes models with no official USD price. "
                "It is not a cap and not a billed amount."
            ),
        },
    }
