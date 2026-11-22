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
                                      service="payments-service", scenario="db_pool_exhaustion"), notify=False)
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
                                      service="payments-service", scenario="db_pool_exhaustion"), notify=False)
    assert a.status == "approved"
    assert a.tokens == 30


def test_graph_has_expected_nodes(orch):
    nodes = set(orch.graph.get_graph().nodes)
    assert {"triage", "gather", "investigate", "verify", "respond"} <= nodes
