import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from app import config
from app.orchestrator import Orchestrator
from app.schemas import AskRequest, FinalAnswer

app = FastAPI(title="OnCall Copilot")
_orch: Orchestrator | None = None
_hits: dict[str, deque] = defaultdict(deque)


def orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch


def current_user(x_api_key: str = Header(default="")) -> dict:
    user = config.USERS.get(x_api_key)
    if not user:
        raise HTTPException(401, "invalid api key")
    q, now = _hits[user["name"]], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(429, "rate limit exceeded")
    q.append(now)
    return user


@app.get("/health")
def health():
    return {"ok": True, "scenario": config.active_scenario() or "default"}


@app.post("/ask", response_model=FinalAnswer)
def ask(req: AskRequest, debug: bool = False, user: dict = Depends(current_user),
        orch: Orchestrator = Depends(orchestrator)):
    if req.service and req.service not in user["services"]:
        raise HTTPException(403, "service not permitted")
    try:
        answer = orch.handle(user, req)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    with_trace = debug and user["role"] == "admin"
    if with_trace:
        orch.audit.write(answer.incident_id, "trace_returned", user["name"], {"events": len(answer.trace)})
    return JSONResponse(answer.model_dump(mode="json", exclude=None if with_trace else {"trace"}))


@app.get("/audit/{incident_id}")
def audit(incident_id: str, user: dict = Depends(current_user), orch: Orchestrator = Depends(orchestrator)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    return {"chain_valid": orch.audit.verify(), "events": orch.audit.read(incident_id)}
