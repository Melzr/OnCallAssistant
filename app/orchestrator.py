import hashlib
import time
import uuid

from app import config
from app.actions import slack
from app.agents import investigator, responder, triage, verifier
from app.rag.retriever import Retriever
from app.schemas import AskRequest, FinalAnswer
from app.security.audit import AuditLog
from app.security.filters import check_input
from simulator import scenarios


class Orchestrator:
    def __init__(self, retriever: Retriever | None = None, audit: AuditLog | None = None):
        self.retriever = retriever or Retriever()
        self.audit = audit or AuditLog()
        self._cache: dict[str, tuple[float, FinalAnswer]] = {}

    def _cache_key(self, user: dict, req: AskRequest) -> str:
        scope = ",".join(sorted(user["groups"]))
        raw = f"{req.service}|{req.scenario}|{' '.join(req.question.lower().split())}|{scope}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def handle(self, user: dict, req: AskRequest, notify: bool = True) -> FinalAnswer:
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        who = user["name"]
        trace: list[dict] = []
        tokens = 0

        def log(event: str, data: dict) -> None:
            trace.append({"event": event, **data})
            self.audit.write(incident_id, event, who, data)

        ok, reason = check_input(req.question, config.MAX_QUESTION_CHARS)
        if not ok:
            log("input_blocked", {"reason": reason})
            raise ValueError(reason)

        key = self._cache_key(user, req)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < config.CACHE_TTL_SECONDS:
            log("cache_hit", {"key": key[:12]})
            return hit[1].model_copy(update={"incident_id": incident_id, "cached": True})

        plan, t = triage.run(req.question, req.service, user["services"])
        tokens += t
        log("plan", plan.model_dump())

        env = scenarios.build(req.scenario or _default_scenario(plan.service))
        evidence = investigator.gather(env, plan, user["services"])
        docs = investigator.sanitize_docs(investigator.retrieve(self.retriever, plan, evidence, user["groups"]))
        log("evidence", {"ids": [e.id for e in evidence], "docs": [d["id"] for d in docs]})

        critique, h, rounds = None, None, 0
        for rounds in range(1, config.MAX_VERIFY_ROUNDS + 1):
            if tokens > config.TOKEN_BUDGET_PER_INCIDENT:
                log("budget_exceeded", {"tokens": tokens})
                break
            h, t = investigator.run(plan, evidence, docs, critique, severity_low=plan.severity == "low")
            tokens += t
            docs = _merge(docs, self.retriever.search(
                plan.incident_goal, groups=user["groups"], service=plan.service,
                intent=plan.intent, category=h.category))
            log("hypothesis", h.model_dump())
            critique, t = verifier.run(h, evidence, docs)
            tokens += t
            log("critique", critique.model_dump())
            if critique.approved:
                break

        if h is None:
            raise RuntimeError("token budget exceeded before any hypothesis")
        answer = responder.run(incident_id, plan, h, bool(critique and critique.approved), rounds, evidence, docs)
        answer.tokens = tokens
        answer.trace = trace
        if answer.status == "approved":
            self._cache[key] = (time.time(), answer)
        if notify:
            log("slack", slack.post(answer))
        log("final", {"status": answer.status, "category": answer.category, "tokens": tokens})
        return answer


def _merge(a: list[dict], b: list[dict]) -> list[dict]:
    seen = {d["id"] for d in a}
    return a + [d for d in b if d["id"] not in seen]


def _default_scenario(service: str) -> str:
    for sid in scenarios.scenario_ids():
        if scenarios.build(sid).service == service:
            return sid
    raise KeyError(f"no simulated scenario for {service}")
