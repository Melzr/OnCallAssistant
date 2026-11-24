import hashlib
import time
import uuid

from app import config, tracing
from app.graph import build_graph
from app.rag.retriever import Retriever
from app.schemas import AskRequest, FinalAnswer
from app.security.audit import AuditLog
from app.security.filters import check_input


class Orchestrator:
    def __init__(self, retriever: Retriever | None = None, audit: AuditLog | None = None):
        self.retriever = retriever or Retriever()
        self.audit = audit or AuditLog()
        tracing.setup()
        self.graph = build_graph(self.retriever)
        self._cache: dict[str, tuple[float, FinalAnswer]] = {}

    def _cache_key(self, user: dict, req: AskRequest) -> str:
        scope = ",".join(sorted(user["groups"]))
        raw = f"{req.service}|{config.active_scenario()}|{' '.join(req.question.lower().split())}|{scope}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def handle(self, user: dict, req: AskRequest) -> FinalAnswer:
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
            return hit[1].model_copy(update={"incident_id": incident_id, "cached": True, "trace": trace})

        final = self.graph.invoke(
            {"incident_id": incident_id, "user": user, "req": req, "tokens": 0},
            tracing.run_config(incident_id, who, log))
        answer = final["answer"]
        tokens = answer.tokens
        answer.trace = trace
        if answer.status == "approved":
            self._cache[key] = (time.time(), answer)
        log("final", {"status": answer.status, "category": answer.category, "tokens": tokens})
        return answer

