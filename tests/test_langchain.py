import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app import llm
from app.schemas import AskRequest, Critique, Hypothesis, Plan

REPLIES = {
    Plan: {"incident_goal": "fix payments", "service": "payments-service", "severity": "high",
           "intent": "mitigation", "tools": []},
    Hypothesis: {"root_cause": "Connection pool to the database is exhausted", "category": "db_pool_exhaustion",
                 "confidence": 0.5, "evidence_ids": ["E1", "E2"],
                 "citations": ["rb-payments-db-pool#diagnosis"]},
    Critique: {"approved": True, "issues": [], "score": 1.0},
}


def fake_chat_factory(refuse_for=None):
    def make(model, max_tokens, effort, schema):
        stop = "refusal" if schema is refuse_for else "end_turn"
        msg = AIMessage(content=json.dumps(REPLIES[schema]), response_metadata={"stop_reason": stop},
                        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
        return GenericFakeChatModel(messages=iter([msg]))
    return make


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def test_online_path_traces_llm_calls(monkeypatch, online, orch, alice):
    monkeypatch.setattr(llm, "make_chat", fake_chat_factory())
    a = orch.handle(alice, AskRequest(question="payments-service is down, how do I fix it?",
                                      service="payments-service"))
    assert a.status == "approved"
    assert a.tokens == 45
    events = [t["event"] for t in a.trace]
    assert events.count("llm_call") == 3
    assert "tool_call" in events
    tools = {t["tool"] for t in a.trace if t["event"] == "tool_call"}
    assert {"query_metrics", "search_logs", "recent_deploys"} <= tools


def test_refusal_falls_back_to_heuristics(monkeypatch, online, orch, alice):
    monkeypatch.setattr(llm, "make_chat", fake_chat_factory(refuse_for=Hypothesis))
    a = orch.handle(alice, AskRequest(question="payments-service is down, how do I fix it?",
                                      service="payments-service"))
    assert a.status == "approved"
    assert a.tokens == 30


def test_graph_has_expected_nodes(orch):
    nodes = set(orch.graph.get_graph().nodes)
    assert {"triage", "gather", "investigate", "verify", "respond"} <= nodes


def test_base_url_and_headers_reach_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.example")
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "x-client-id: claude")
    chat = llm.make_chat("claude-haiku-5-5", 100, "low", Plan)
    assert chat.anthropic_api_url == "https://gateway.example"
    assert chat.default_headers == {"x-client-id": "claude"}


def test_schema_is_closed_and_unconstrained():
    from app.schemas import Hypothesis as H
    s = llm.strict_schema(H.model_json_schema())
    assert s["additionalProperties"] is False
    assert "minimum" not in json.dumps(s) and "maximum" not in json.dumps(s)
    assert "properties" in s and "confidence" in s["properties"]


def test_llm_errors_fall_back_to_heuristics(monkeypatch, online, orch, alice):
    class Broken:
        def __or__(self, other):
            raise RuntimeError("gateway 400")

    monkeypatch.setattr(llm, "make_chat", lambda *a, **k: Broken())
    a = orch.handle(alice, AskRequest(question="payments-service is down, how do I fix it?",
                                      service="payments-service"))
    assert a.status == "approved"
    assert a.tokens == 0


def test_investigator_escalates_to_opus_only_after_rejection(monkeypatch, online, orch, alice):
    from app import config
    used = []
    bad = {**REPLIES[Hypothesis], "category": "made_up"}
    seq = {"inv": 0}

    def make(model, max_tokens, effort, schema):
        used.append(model)
        reply = REPLIES[schema]
        if schema is Hypothesis:
            reply = bad if seq["inv"] == 0 else REPLIES[Hypothesis]
            seq["inv"] += 1
        msg = AIMessage(content=json.dumps(reply), response_metadata={"stop_reason": "end_turn"})
        return GenericFakeChatModel(messages=iter([msg]))

    monkeypatch.setattr(llm, "make_chat", make)
    orch.handle(alice, AskRequest(question="payments-service is down, how do I fix it?",
                                  service="payments-service"))
    inv = [m for m in used if m in (config.MODEL_INVESTIGATOR, config.MODEL_INVESTIGATOR_ESCALATION)]
    assert inv[0] == config.MODEL_INVESTIGATOR
    assert inv[1] == config.MODEL_INVESTIGATOR_ESCALATION


def test_prompt_docs_are_trimmed_but_keep_citations():
    from app import config
    from app.agents.context import render_docs
    docs = [{"id": f"d#{i}", "header": f"h{i}", "text": "x" * 5000, "score": 1 - i / 10} for i in range(8)]
    out = render_docs(docs, keep=("d#7",))
    assert out.count("[truncated]") == config.MAX_PROMPT_DOCS + 1
    assert "[d#0]" in out and "[d#7]" in out and "[d#5]" not in out
    assert len(out) < (config.MAX_PROMPT_DOCS + 1) * (config.MAX_DOC_CHARS + 100)
