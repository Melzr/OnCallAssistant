import os
import time
from typing import Callable

from langchain_core.callbacks import BaseCallbackHandler


def langsmith_enabled() -> bool:
    return bool(os.environ.get("LANGSMITH_API_KEY"))


def setup() -> None:
    if langsmith_enabled():
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "oncall-assistant")


class TraceHandler(BaseCallbackHandler):
    """Forwards LLM and tool calls to a sink (trace + audit log). Prompt text is never recorded."""

    def __init__(self, sink: Callable[[str, dict], None]):
        self.sink = sink
        self._start: dict = {}

    def _ms(self, run_id) -> int:
        return int((time.time() - self._start.pop(run_id, time.time())) * 1000)

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._start[run_id] = time.time()

    def on_llm_end(self, response, *, run_id, **kwargs):
        msg = response.generations[0][0].message
        usage = getattr(msg, "usage_metadata", None) or {}
        meta = getattr(msg, "response_metadata", {}) or {}
        self.sink("llm_call", {"model": meta.get("model_name") or meta.get("model", "unknown"),
                               "tokens": usage.get("total_tokens", 0),
                               "input_tokens": usage.get("input_tokens", 0),
                               "output_tokens": usage.get("output_tokens", 0), "ms": self._ms(run_id),
                               "stop_reason": meta.get("stop_reason")})

    def on_llm_error(self, error, *, run_id, **kwargs):
        self.sink("llm_error", {"error": type(error).__name__, "detail": str(error)[:200], "ms": self._ms(run_id)})

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        self._start[run_id] = time.time()
        self._tool_input = input_str

    def on_tool_end(self, output, *, run_id, name=None, **kwargs):
        self.sink("tool_call", {"tool": name, "input": str(self._tool_input)[:200], "ms": self._ms(run_id)})

    def on_tool_error(self, error, *, run_id, name=None, **kwargs):
        self.sink("tool_error", {"tool": name, "error": type(error).__name__, "ms": self._ms(run_id)})


def run_config(incident_id: str, user: str, log: Callable[[str, dict], None]) -> dict:
    return {
        "run_name": "oncall-assistant",
        "callbacks": [TraceHandler(log)],
        "tags": ["oncall-assistant"],
        "metadata": {"incident_id": incident_id, "user": user},
        "configurable": {"log": log},
    }
