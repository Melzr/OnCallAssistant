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
            "format": {"type": "json_schema", "schema": schema.model_json_schema()},
        },
    )


def _parser(schema: type[T]) -> RunnableLambda:
    def parse(msg: AIMessage) -> tuple[T, int]:
        if msg.response_metadata.get("stop_reason") == "refusal":
            raise LLMRefusal(str(msg.response_metadata.get("stop_details")))
        tokens = (msg.usage_metadata or {}).get("total_tokens", 0)
        return schema.model_validate_json(msg.text), tokens

    return RunnableLambda(parse, name="parse_json")


def complete_json(*, model: str, system: str, user: str, schema: type[T], max_tokens: int = 2000,
                  effort: str = "low", name: str = "llm") -> tuple[T, int]:
    """Run a chat -> schema-validating chain and return the object plus tokens used."""
    if not online():
        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
    chain = (make_chat(model, max_tokens, effort, schema) | _parser(schema)).with_config(run_name=name)
    return chain.invoke([SystemMessage(system), HumanMessage(user)])
