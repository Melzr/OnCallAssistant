import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableConfig

from app import config as settings
from app.agents import investigator, responder, triage, verifier
from app.rag.retriever import Retriever
from app.schemas import AskRequest, Critique, Evidence, FinalAnswer, Hypothesis, Plan
from simulator import scenarios


class State(TypedDict, total=False):
    incident_id: str
    user: dict
    req: AskRequest
    plan: Plan
    evidence: list[Evidence]
    docs: list[dict]
    hypothesis: Hypothesis
    critique: Critique
    rounds: int
    tokens: int
    answer: FinalAnswer


def _log(config: RunnableConfig):
    return config["configurable"]["log"]


def _default_scenario(service: str) -> str:
    for sid in scenarios.scenario_ids():
        if scenarios.build(sid).service == service:
            return sid
    raise KeyError(f"no simulated scenario for {service}")


def _merge(a: list[dict], b: list[dict]) -> list[dict]:
    seen = {d["id"] for d in a}
    return a + [d for d in b if d["id"] not in seen]


def build_graph(retriever: Retriever):
    def triage_node(s: State, config: RunnableConfig):
        plan, t = triage.run(s["req"].question, s["req"].service, s["user"]["services"])
        _log(config)("plan", plan.model_dump())
        return {"plan": plan, "tokens": s.get("tokens", 0) + t}

    def gather_node(s: State, config: RunnableConfig):
        plan, user = s["plan"], s["user"]
        env = scenarios.build(s["req"].scenario or _default_scenario(plan.service))
        evidence = investigator.gather(env, plan, user["services"])
        docs = investigator.sanitize_docs(investigator.retrieve(retriever, plan, evidence, user["groups"]))
        _log(config)("evidence", {"ids": [e.id for e in evidence], "docs": [d["id"] for d in docs]})
        return {"evidence": evidence, "docs": docs, "rounds": 0}

    def investigate_node(s: State, config: RunnableConfig):
        plan, user = s["plan"], s["user"]
        if s["tokens"] > settings.TOKEN_BUDGET_PER_INCIDENT and "hypothesis" not in s:
            raise RuntimeError("token budget exceeded before any hypothesis")
        h, t = investigator.run(plan, s["evidence"], s["docs"], s.get("critique"))
        docs = _merge(s["docs"], retriever.search(
            plan.incident_goal, groups=user["groups"], service=plan.service,
            intent=plan.intent, category=h.category))
        _log(config)("hypothesis", h.model_dump())
        return {"hypothesis": h, "docs": docs, "rounds": s["rounds"] + 1, "tokens": s["tokens"] + t}

    def verify_node(s: State, config: RunnableConfig):
        critique, t = verifier.run(s["hypothesis"], s["evidence"], s["docs"])
        _log(config)("critique", critique.model_dump())
        return {"critique": critique, "tokens": s["tokens"] + t}

    def after_verify(s: State, config: RunnableConfig) -> str:
        if s["critique"].approved or s["rounds"] >= settings.MAX_VERIFY_ROUNDS:
            return "respond"
        if s["tokens"] > settings.TOKEN_BUDGET_PER_INCIDENT:
            _log(config)("budget_exceeded", {"tokens": s["tokens"]})
            return "respond"
        return "investigate"

    def respond_node(s: State, config: RunnableConfig):
        answer = responder.run(s["incident_id"], s["plan"], s["hypothesis"], s["critique"].approved,
                               s["rounds"], s["evidence"], s["docs"])
        answer.tokens = s["tokens"]
        return {"answer": answer}

    def timed(name, fn):
        def node(s: State, config: RunnableConfig):
            t0 = time.time()
            out = fn(s, config)
            _log(config)("node", {"node": name, "ms": int((time.time() - t0) * 1000)})
            return out
        return node

    g = StateGraph(State)
    g.add_node("triage", timed("triage", triage_node))
    g.add_node("gather", timed("gather", gather_node))
    g.add_node("investigate", timed("investigate", investigate_node))
    g.add_node("verify", timed("verify", verify_node))
    g.add_node("respond", timed("respond", respond_node))
    g.add_edge(START, "triage")
    g.add_edge("triage", "gather")
    g.add_edge("gather", "investigate")
    g.add_edge("investigate", "verify")
    g.add_conditional_edges("verify", after_verify, {"investigate": "investigate", "respond": "respond"})
    g.add_edge("respond", END)
    return g.compile()
