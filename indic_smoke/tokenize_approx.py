"""Approximate prompt-token counts.

Tokenizer: tiktoken encoding `o200k_base` (used by recent OpenAI GPT models).
This is an approximation for every model in the set, including Gemini, Qwen,
DeepSeek, and the System One decision models, whose billed tokenizers are not
the same. Indic text in particular may tokenize differently on those systems.
Counts are labeled as approximations in the estimate output.
"""

from __future__ import annotations

import json
from typing import Any

import tiktoken

from indic_smoke.task import SENTIMENT, TaskSpec

ENCODING_NAME = "o200k_base"
_ENCODER = None


def encoder():
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding(ENCODING_NAME)
    return _ENCODER


def count_tokens(text: str) -> int:
    return len(encoder().encode(text))


def decisions_prompt_text(review: str, task: TaskSpec = SENTIMENT) -> str:
    """Compact JSON of the Decisions/System One payload (state + questions).

    This is not the provider's internal prompt. It is a consistent, inspectable
    stand-in for 'the request the model is billed on'.
    """
    return json.dumps(task.decisions_payload(review), ensure_ascii=False, separators=(",", ":"))


def chat_prompt_text(review: str, task: TaskSpec = SENTIMENT) -> str:
    """A flattened stand-in for a chat + json_schema request.

    Roles are marked explicitly. This is not OpenAI's exact tokenization of a
    chat message list, but it includes the system text, the review, and the
    schema that will be sent.
    """
    parts = []
    for message in task.llm_messages(review):
        parts.append(f"<|{message['role']}|>{message['content']}")
    parts.append("<|schema|>" + json.dumps(task.llm_response_format(), ensure_ascii=False, separators=(",", ":")))
    return "\n".join(parts)


def assumed_structured_output_text(task: TaskSpec = SENTIMENT) -> str:
    return task.assumed_structured_output_text()


def token_report(review: str, task: TaskSpec = SENTIMENT) -> dict[str, Any]:
    dec = decisions_prompt_text(review, task)
    chat = chat_prompt_text(review, task)
    out = assumed_structured_output_text(task)
    return {
        "decisions_prompt_tokens": count_tokens(dec),
        "chat_prompt_tokens": count_tokens(chat),
        "assumed_structured_output_tokens": count_tokens(out),
        "review_tokens_only": count_tokens(review),
    }
