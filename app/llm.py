from typing import TypeVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from app import config

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    pass


class LLMRefusal(Exception):
    pass


def online() -> bool:
    return config.anthropic_key() is not None


_UNSUPPORTED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
                "minItems", "maxItems", "title", "default"}


def strict_schema(node):
    """Adapts a pydantic JSON schema to the structured-output subset (closed objects, no constraints)."""
    if isinstance(node, list):
        return [strict_schema(n) for n in node]
    if not isinstance(node, dict):
        return node
    out = {k: strict_schema(v) for k, v in node.items() if k not in _UNSUPPORTED or k == "properties"}
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


def make_chat(model: str, max_tokens: int, effort: str, schema: type[BaseModel]):
    from langchain_anthropic import ChatAnthropic

    extra = {}
    if base_url := config.anthropic_base_url():
        extra["base_url"] = base_url
    if headers := config.anthropic_headers():
        extra["default_headers"] = headers
    return ChatAnthropic(
        model=model,
        max_tokens=max_tokens,
        **extra,
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": strict_schema(schema.model_json_schema())},
        },
    )


def _parser(schema: type[T]) -> RunnableLambda:
    def parse(msg: AIMessage) -> tuple[T, int]:
        if msg.response_metadata.get("stop_reason") == "refusal":
            raise LLMRefusal(str(msg.response_metadata.get("stop_details")))
        tokens = (msg.usage_metadata or {}).get("total_tokens", 0)
        return schema.model_validate_json(msg.text), tokens

    return RunnableLambda(parse, name="parse_json")


CACHE_BUST = ""  # unique value defeats gateway-side response caching (used by benchmarks)


def complete_json(*, model: str, system: str, user: str, schema: type[T], max_tokens: int = 2000,
                  effort: str = "low", name: str = "llm") -> tuple[T, int]:
    """Run a chat -> schema-validating chain and return the object plus tokens used."""
    if not online():
        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
    try:
        chain = (make_chat(model, max_tokens, effort, schema) | _parser(schema)).with_config(run_name=name)
        return chain.invoke([SystemMessage(system + (f"\n[request {CACHE_BUST}]" if CACHE_BUST else "")), HumanMessage(user)])
    except LLMRefusal:
        raise
    except Exception as e:
        raise LLMUnavailable(f"{type(e).__name__}: {str(e)[:200]}") from e
