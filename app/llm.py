import json
from typing import TypeVar

from pydantic import BaseModel

from app import config

T = TypeVar("T", bound=BaseModel)

_client = None


class LLMUnavailable(Exception):
    pass


class LLMRefusal(Exception):
    pass


def online() -> bool:
    return config.anthropic_key() is not None


def _get_client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()
    return _client


def complete_json(*, model: str, system: str, user: str, schema: type[T],
                  max_tokens: int = 2000, effort: str = "low") -> tuple[T, int]:
    """Call Claude and return a validated schema instance plus tokens used."""
    if not online():
        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
    resp = _get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": schema.model_json_schema()},
        },
    )
    if resp.stop_reason == "refusal":
        raise LLMRefusal(str(getattr(resp, "stop_details", None)))
    text = next(b.text for b in resp.content if b.type == "text")
    tokens = resp.usage.input_tokens + resp.usage.output_tokens
    return schema.model_validate(json.loads(text)), tokens
