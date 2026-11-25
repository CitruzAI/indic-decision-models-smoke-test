"""Model registry built from the committed OpenRouter snapshot and public docs.

No live prices are invented here. Missing prices are marked explicitly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "catalog" / "openrouter_snapshot.json"

Family = Literal["decisions", "chat"]
Provider = Literal["openrouter", "sarvam", "baseten"]


@dataclass(frozen=True)
class ModelSpec:
    key: str
    display_name: str
    model_id: str
    provider: Provider
    family: Family
    endpoint: str
    auth_env: str
    # USD per token, or None if unknown
    prompt_usd_per_token: Decimal | None
    completion_usd_per_token: Decimal | None
    request_usd: Decimal
    price_source: str
    price_found: bool
    runnable_id_confirmed: bool
    notes: list[str] = field(default_factory=list)
    # Chat-only
    supports_structured_outputs: bool = False
    supports_logprobs: bool = False
    reasoning: dict[str, Any] | None = None
    # For live calls: disable reasoning when the model allows it
    reasoning_effort: str | None = None

    @property
    def prompt_usd_per_1m(self) -> Decimal | None:
        if self.prompt_usd_per_token is None:
            return None
        return self.prompt_usd_per_token * Decimal("1000000")

    @property
    def completion_usd_per_1m(self) -> Decimal | None:
        if self.completion_usd_per_token is None:
            return None
        return self.completion_usd_per_token * Decimal("1000000")


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _or_prices(snapshot: dict[str, Any], model_id: str, bucket: str) -> dict[str, Any] | None:
    return (snapshot.get(bucket) or {}).get(model_id, {}).get("pricing")


def registry(snapshot: dict[str, Any] | None = None) -> list[ModelSpec]:
    """The models named in the brief, plus confirmed sibling ids where needed."""
    snap = snapshot or load_snapshot()
    chat = snap["chat_models"]
    dec = snap["decision_models"]
    endpoints = snap["endpoints"]

    def or_prompt(mid: str, bucket: str) -> Decimal:
        pricing = _or_prices(snap, mid, bucket)
        if not pricing or "prompt" not in pricing:
            raise KeyError(mid)
        return _dec(pricing["prompt"])

    def or_completion(mid: str, bucket: str) -> Decimal:
        pricing = _or_prices(snap, mid, bucket)
        return _dec(pricing.get("completion") or "0")

    pplx_flash_eps = (endpoints.get("perplexity/pplx-decider-flash-v1.3") or {}).get("n_endpoints", 0)
    pplx_full_eps = (endpoints.get("perplexity/pplx-decider-v1.3") or {}).get("n_endpoints", 0)

    specs = [
        ModelSpec(
            key="jev",
            display_name="TypeSafe Jev 1.14",
            model_id="typesafe/jev-1.14",
            provider="openrouter",
            family="decisions",
            endpoint="https://openrouter.ai/api/alpha/decisions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=or_prompt("typesafe/jev-1.14", "decision_models"),
            completion_usd_per_token=or_completion("typesafe/jev-1.14", "decision_models"),
            request_usd=Decimal("0"),
            price_source="OpenRouter GET /api/v1/models?output_modalities=decisions (snapshot in catalog/)",
            price_found=True,
            runnable_id_confirmed=True,
            notes=[
                "Listed in the Decisions catalog, not in the unfiltered chat-model list.",
                f"Canonical slug {dec['typesafe/jev-1.14'].get('canonical_slug')}.",
                "Output tokens are priced at $0 on this endpoint.",
            ],
        ),
        ModelSpec(
            key="msdecision",
            display_name="Microsoft Decision 1.1",
            model_id="microsoft/microsoft-decision-1.1",
            provider="openrouter",
            family="decisions",
            endpoint="https://openrouter.ai/api/alpha/decisions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=or_prompt("microsoft/microsoft-decision-1.1", "decision_models"),
            completion_usd_per_token=or_completion("microsoft/microsoft-decision-1.1", "decision_models"),
            request_usd=Decimal("0"),
            price_source="OpenRouter GET /api/v1/models?output_modalities=decisions (snapshot in catalog/)",
            price_found=True,
            runnable_id_confirmed=True,
            notes=[
                f"Canonical slug {dec['microsoft/microsoft-decision-1.1'].get('canonical_slug')}.",
                "Output tokens are priced at $0 on this endpoint.",
            ],
        ),
        ModelSpec(
            key="pplx-flash",
            display_name="Perplexity Decider Flash v1.3",
            model_id="perplexity/pplx-decider-flash-v1.3",
            provider="openrouter",
            family="decisions",
            endpoint="https://openrouter.ai/api/alpha/decisions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=None,
            completion_usd_per_token=None,
            request_usd=Decimal("0"),
            price_source="not listed; GET /api/v1/models/<id>/endpoints returned 0 endpoints",
            price_found=False,
            runnable_id_confirmed=False,
            notes=[
                f"The unsuffixed id has a model record but {pplx_flash_eps} endpoints, so it is not a confirmed runnable id.",
                "The Decisions catalog lists perplexity/pplx-decider-flash-v1.3:free at $0 input and $0 output, with 1 Perplexity endpoint.",
                "This harness does not silently substitute the :free id. A later run can target :free explicitly.",
            ],
        ),
        ModelSpec(
            key="pplx-full",
            display_name="Perplexity Decider v1.3",
            model_id="perplexity/pplx-decider-v1.3",
            provider="openrouter",
            family="decisions",
            endpoint="https://openrouter.ai/api/alpha/decisions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=None,
            completion_usd_per_token=None,
            request_usd=Decimal("0"),
            price_source="not listed; GET /api/v1/models/<id>/endpoints returned 0 endpoints",
            price_found=False,
            runnable_id_confirmed=False,
            notes=[
                f"The unsuffixed id has a model record but {pplx_full_eps} endpoints, so it is not a confirmed runnable id.",
                "The Decisions catalog lists perplexity/pplx-decider-v1.3:free at $0 input and $0 output, with 1 Perplexity endpoint.",
                "This harness does not silently substitute the :free id. A later run can target :free explicitly.",
            ],
        ),
        ModelSpec(
            key="gemini",
            display_name="Gemini 4 Hydrogen",
            model_id="google/gemini-4-hydrogen",
            provider="openrouter",
            family="chat",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=_dec(chat["google/gemini-4-hydrogen"]["pricing"]["prompt"]),
            completion_usd_per_token=_dec(chat["google/gemini-4-hydrogen"]["pricing"]["completion"]),
            request_usd=Decimal("0"),
            price_source="OpenRouter GET /api/v1/models (snapshot in catalog/)",
            price_found=True,
            runnable_id_confirmed=True,
            supports_structured_outputs=True,
            supports_logprobs=False,
            reasoning=chat["google/gemini-4-hydrogen"].get("reasoning"),
            reasoning_effort=None,  # mandatory; cannot set none
            notes=[
                f"Canonical slug {chat['google/gemini-4-hydrogen'].get('canonical_slug')}.",
                "Reasoning is mandatory (default effort medium). internal_reasoning is billed at the completion rate.",
                "supported_parameters includes response_format and structured_outputs, not logprobs.",
                "Prompt-only cost is an underestimate; reasoning tokens were not guessed.",
            ],
        ),
        ModelSpec(
            key="gpt-sol",
            display_name="GPT-6.2 Sol",
            model_id="openai/gpt-6.2-sol",
            provider="openrouter",
            family="chat",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=_dec(chat["openai/gpt-6.2-sol"]["pricing"]["prompt"]),
            completion_usd_per_token=_dec(chat["openai/gpt-6.2-sol"]["pricing"]["completion"]),
            request_usd=Decimal("0"),
            price_source="OpenRouter GET /api/v1/models (snapshot in catalog/)",
            price_found=True,
            runnable_id_confirmed=True,
            supports_structured_outputs=True,
            supports_logprobs=False,
            reasoning=chat["openai/gpt-6.2-sol"].get("reasoning"),
            reasoning_effort=None,
            notes=[
                f"Canonical slug {chat['openai/gpt-6.2-sol'].get('canonical_slug')}.",
                "Reasoning is mandatory (default effort medium).",
                "supported_parameters includes response_format and structured_outputs, not logprobs.",
                "Prompt-only cost is an underestimate; reasoning tokens were not guessed.",
            ],
        ),
        ModelSpec(
            key="gpt-luna",
            display_name="GPT-6 Luna",
            model_id="openai/gpt-6-luna",
            provider="openrouter",
            family="chat",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=_dec(chat["openai/gpt-6-luna"]["pricing"]["prompt"]),
            completion_usd_per_token=_dec(chat["openai/gpt-6-luna"]["pricing"]["completion"]),
            request_usd=Decimal("0"),
            price_source="OpenRouter GET /api/v1/models (snapshot in catalog/)",
            price_found=True,
            runnable_id_confirmed=True,
            supports_structured_outputs=True,
            supports_logprobs=False,
            reasoning=chat["openai/gpt-6-luna"].get("reasoning"),
            reasoning_effort="none",
            notes=[
                f"Canonical slug {chat['openai/gpt-6-luna'].get('canonical_slug')}.",
                "Reasoning is optional; the harness sets reasoning_effort=none.",
                "supported_parameters includes response_format and structured_outputs, not logprobs.",
            ],
        ),
        ModelSpec(
            key="qwen",
            display_name="Qwen4 Max",
            model_id="qwen/qwen4-max",
            provider="openrouter",
            family="chat",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=_dec(chat["qwen/qwen4-max"]["pricing"]["prompt"]),
            completion_usd_per_token=_dec(chat["qwen/qwen4-max"]["pricing"]["completion"]),
            request_usd=Decimal("0"),
            price_source="OpenRouter GET /api/v1/models (snapshot in catalog/)",
            price_found=True,
            runnable_id_confirmed=True,
            supports_structured_outputs=True,
            supports_logprobs=True,
            reasoning=chat["qwen/qwen4-max"].get("reasoning"),
            reasoning_effort="none",
            notes=[
                f"Canonical slug {chat['qwen/qwen4-max'].get('canonical_slug')}.",
                "Reasoning defaults to high; the harness sets reasoning_effort=none.",
                "logprobs and structured_outputs are both in supported_parameters.",
            ],
        ),
        ModelSpec(
            key="deepseek",
            display_name="DeepSeek V4.1 Flash 1017",
            model_id="deepseek/deepseek-v4.1-flash-1017",
            provider="openrouter",
            family="chat",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            auth_env="OPENROUTER_API_KEY",
            prompt_usd_per_token=_dec(chat["deepseek/deepseek-v4.1-flash-1017"]["pricing"]["prompt"]),
            completion_usd_per_token=_dec(chat["deepseek/deepseek-v4.1-flash-1017"]["pricing"]["completion"]),
            request_usd=Decimal("0"),
            price_source="OpenRouter GET /api/v1/models (snapshot in catalog/)",
            price_found=True,
            runnable_id_confirmed=True,
            supports_structured_outputs=True,
            supports_logprobs=True,
            reasoning=chat["deepseek/deepseek-v4.1-flash-1017"].get("reasoning"),
            reasoning_effort="none",
            notes=[
                f"Canonical slug {chat['deepseek/deepseek-v4.1-flash-1017'].get('canonical_slug')}.",
                "Reasoning defaults to high; the harness sets reasoning_effort=none.",
                "logprobs is in the model-level supported_parameters; some providers omit it.",
            ],
        ),
        ModelSpec(
            key="sarvam",
            display_name="Sarvam Prism",
            model_id="sarvam-prism",
            provider="sarvam",
            family="decisions",
            endpoint="https://api.sarvam.ai/v2/systemone",
            auth_env="SARVAM_API_KEY",
            prompt_usd_per_token=None,
            completion_usd_per_token=None,
            request_usd=Decimal("0"),
            price_source="Sarvam docs (https://docs.sarvam.ai/api/token-factory/models/sarvam-prism): ₹4 per 1M input tokens, ₹0 per 1M output, on every plan. No official USD list price.",
            price_found=False,  # no official USD
            runnable_id_confirmed=True,
            notes=[
                "Official price is in INR, not USD, so it is excluded from the USD total.",
                "Auth: api-subscription-key: $SARVAM_API_KEY, or Authorization: Bearer $SARVAM_API_KEY.",
                "Docs list English, 10 Indian languages, and Hinglish.",
            ],
        ),
        ModelSpec(
            key="bison",
            display_name="Baseten bison-1",
            model_id="decision-models/baseten-bison-latest",
            provider="baseten",
            family="decisions",
            endpoint="https://inference.baseten.co/v1/systemone",
            auth_env="BASETEN_API_KEY",
            prompt_usd_per_token=Decimal("0.0000001"),  # $0.10 / 1M
            completion_usd_per_token=Decimal("0"),
            request_usd=Decimal("0"),
            price_source="Baseten model card / HF baselabs/bison-1: $0.10 per 1M tokens. OpenRouter lists the same rate for baseten/bison-1, but this harness calls Baseten directly.",
            price_found=True,
            runnable_id_confirmed=True,
            notes=[
                "API reference uses Authorization: Bearer $BASETEN_API_KEY; the model-library curl example uses Authorization: Api-Key. The adapter sends Bearer and can fall back to Api-Key.",
                "Not called through OpenRouter even though baseten/bison-1 exists there.",
            ],
        ),
    ]
    return specs


def by_key(key: str, snapshot: dict[str, Any] | None = None) -> ModelSpec:
    for spec in registry(snapshot):
        if spec.key == key or spec.model_id == key:
            return spec
    raise KeyError(key)
