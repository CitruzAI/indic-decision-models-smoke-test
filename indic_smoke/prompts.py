"""Shared prompts. Instructions are in English for every language of the review.

Only the review text changes across en/hi/ta, so a hi-vs-en or ta-vs-en drop is
not confounded by a different question wording.
"""

from __future__ import annotations

from typing import Any

LABELS = ("Positive", "Negative")

CHOICE_INSTRUCTIONS = (
    "Classify the sentiment of this product review toward the product or service."
)
CHOICE_CRITERIA = {
    "Positive": "The review expresses a positive sentiment toward the product or service.",
    "Negative": "The review expresses a negative sentiment toward the product or service.",
}

LLM_SYSTEM = (
    "You classify product-review sentiment. "
    "Reply with a JSON object that has a single field, label, "
    "which must be exactly one of: Positive, Negative. "
    "Do not include explanations or a self-reported confidence score."
)

SENTIMENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": list(LABELS)},
    },
    "required": ["label"],
    "additionalProperties": False,
}


def decisions_payload(text: str) -> dict[str, Any]:
    """Body for a System One / Decisions request, minus the model field."""
    return {
        "state": text,
        "questions": {
            "sentiment": {
                "type": "choice",
                "instructions": CHOICE_INSTRUCTIONS,
                "criteria": dict(CHOICE_CRITERIA),
            }
        },
    }


def llm_messages(text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": LLM_SYSTEM},
        {"role": "user", "content": f"Review:\n{text}"},
    ]


def llm_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "sentiment_label",
            "strict": True,
            "schema": SENTIMENT_JSON_SCHEMA,
        },
    }
