# OnCall Copilot

Multi-agent incident response assistant (POC). Given an alert or a question, it gathers metrics, logs and
deploys from a simulated environment, retrieves runbooks/postmortems with a metadata-aware RAG, proposes a
root cause, has a second agent verify it, and returns a cited answer.

## Flow

```
request -> auth/RBAC -> input filter -> Triage -> tools + RAG -> Investigator <-> Verifier (max 2 rounds)
        -> Responder (mitigation quoted from a current runbook) -> audit log
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

## Status

Implemented: FastAPI (`/ask`, `/alerts` with HMAC, `/audit/{id}`), 4 agents, simulator, BM25 retriever with
metadata (hard ACL/status filters, soft service filter, related-doc expansion, metadata rerank, enriched index
text), injection filter, redaction, hash-chained audit, response cache, rate limit.

See `THREAT_MODEL.md` for the attack-surface analysis.

## Try it

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q

# simulate incidents in-process (offline, no API key needed)
.venv/bin/python scripts/simulate.py list
.venv/bin/python scripts/simulate.py run all -v
.venv/bin/python scripts/simulate.py attacks

# against a running server
.venv/bin/uvicorn app.api.main:app --reload
.venv/bin/python scripts/simulate.py run bad_deploy --url http://localhost:8000
.venv/bin/python scripts/simulate.py run all --url http://localhost:8000 --alert
```

Audit trail: `var/audit.jsonl`, or `GET /audit/{incident_id}` with an admin key. Set `ANTHROPIC_API_KEY` to enable the LLM layer.

## Agent layer and tracing

Agents run as nodes of a LangGraph `StateGraph` (`app/graph.py`): `triage -> gather -> investigate <-> verify -> respond`. The verify-to-investigate loop is a conditional edge bounded by `MAX_VERIFY_ROUNDS` and the token budget. LLM calls use `ChatAnthropic` (`app/llm.py`); evidence tools are LangChain `StructuredTool`s.

Traceability:
- A callback handler (`app/tracing.py`) records every LLM call (model, tokens, latency, stop reason) and tool call into the response `trace` and the hash-chained audit log. Prompt text is never stored there.
- Set `LANGSMITH_API_KEY` to also send full runs to LangSmith (project `oncall-copilot`, tagged with `incident_id`). Prompts and incident data leave the machine, so keep it unset for sensitive data.

`python scripts/simulate.py graph` prints the graph as mermaid.

## Cost and latency

- **Model cascade:** the investigator starts on Sonnet and escalates to Opus only when the verifier rejects the first hypothesis. Triage uses Haiku.
- **Prompt trimming:** LLM prompts include only the top `MAX_PROMPT_DOCS` retrieved chunks (plus any chunk the hypothesis cites), each cut at `MAX_DOC_CHARS`. The full set is still used for citation checks and for quoting the mitigation.
- **Limits:** response cache (TTL), per-incident token budget, rate limit, max 2 verify rounds.
- **Visibility:** each LLM call records model, tokens and latency in the response `trace`.
