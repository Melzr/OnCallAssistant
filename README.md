# OnCall Copilot

Multi-agent incident response assistant (POC). Given an alert or a question, it gathers metrics, logs and
deploys from a simulated environment, retrieves runbooks/postmortems with a metadata-aware RAG, proposes a
root cause, has a second agent verify it, and posts a summary to Slack.

## Flow

```
request -> auth/RBAC -> input filter -> Triage -> tools + RAG -> Investigator <-> Verifier (max 2 rounds)
        -> Responder (mitigation quoted from a current runbook) -> Slack -> audit log
```

| Agent | Model (online) | Offline fallback |
|---|---|---|
| Triage | claude-haiku-5-5 | keyword heuristics |
| Investigator | claude-opus-5-5 (sonnet for low severity) | rule-based on log templates/deploys |
| Verifier | claude-sonnet-5-5 | deterministic checks only |
| Responder | none: quotes the runbook verbatim | same |

Without `ANTHROPIC_API_KEY` the whole pipeline runs offline with the heuristics. With a key, the LLM calls are
added on top of the same deterministic checks.

## Run

```
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/uvicorn app.api.main:app
curl -s localhost:8000/ask -H 'x-api-key: key-alice-sre' -H 'content-type: application/json' \
  -d '{"question":"payments-service is failing, how do I fix it?","service":"payments-service"}'
```

Scenarios: `db_pool_exhaustion`, `bad_deploy`, `tls_expiry` (see `simulator/scenarios.py`).
Slack messages go to `var/slack_outbox.log` unless `SLACK_WEBHOOK_URL` is set.

## Status

Implemented: FastAPI (`/ask`, `/alerts` with HMAC, `/audit/{id}`), 4 agents, simulator, BM25 retriever with
metadata (hard ACL/status filters, soft service filter, related-doc expansion, metadata rerank, enriched index
text), injection filter, redaction, hash-chained audit, response cache, rate limit, Slack action.

Not yet: dense embeddings + cross-encoder reranker, CLIP chart classifier, LLM tool-use loop (tools run from a
fixed plan), eval harness (recall@k, ROUGE, latency), server-side refusal fallbacks, JWT auth, red-team set.
The online (LLM) path is untested against the real API.

See `THREAT_MODEL.md` for the attack-surface analysis.
