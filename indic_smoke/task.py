"""Use-case task specs: sentiment (default) and support routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from indic_smoke import prompts as sentiment_prompts
from indic_smoke.routing import mapping as routing_mapping


@dataclass(frozen=True)
class TaskSpec:
    key: str
    labels: tuple[str, ...]
    question_name: str
    instructions: str
    criteria: dict[str, str]
    llm_system: str
    user_prefix: str

    def decisions_payload(self, text: str) -> dict[str, Any]:
        return {
            "state": text,
            "questions": {
                self.question_name: {
                    "type": "choice",
                    "instructions": self.instructions,
                    "criteria": dict(self.criteria),
                }
            },
        }

    def llm_messages(self, text: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.llm_system},
            {"role": "user", "content": f"{self.user_prefix}\n{text}"},
        ]

    def llm_response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": f"{self.key}_label",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "enum": list(self.labels)},
                    },
                    "required": ["label"],
                    "additionalProperties": False,
                },
            },
        }

    def assumed_structured_output_text(self) -> str:
        import json

        return json.dumps({"label": self.labels[0]}, separators=(",", ":"))


SENTIMENT = TaskSpec(
    key="sentiment",
    labels=sentiment_prompts.LABELS,
    question_name="sentiment",
    instructions=sentiment_prompts.CHOICE_INSTRUCTIONS,
    criteria=dict(sentiment_prompts.CHOICE_CRITERIA),
    llm_system=sentiment_prompts.LLM_SYSTEM,
    user_prefix="Review:",
)

ROUTING = TaskSpec(
    key="routing",
    labels=routing_mapping.LABELS,
    question_name="route",
    instructions=routing_mapping.CHOICE_INSTRUCTIONS,
    criteria=dict(routing_mapping.CHOICE_CRITERIA),
    llm_system=routing_mapping.LLM_SYSTEM,
    user_prefix=routing_mapping.USER_PREFIX,
)

TASKS = {"sentiment": SENTIMENT, "routing": ROUTING}


def by_name(name: str) -> TaskSpec:
    if name not in TASKS:
        raise KeyError(f"unknown task {name!r}; expected one of {sorted(TASKS)}")
    return TASKS[name]
