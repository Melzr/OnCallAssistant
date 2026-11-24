# Threat model (OWASP LLM Top 10 2025 / Agentic threats / API Security)

Principle: the LLM never enforces security. ACLs, citation validation, and tool arguments
are checked in code.

Trust boundaries: TB1 user -> API; TB2 API -> agents; TB3 agents -> LLM provider; TB4 agents -> tools;
TB5 ingest/RAG/cache; TB6 supply chain.

| # | Surface | Threat | OWASP | Mitigation | Status |
|---|---|---|---|---|---|
| 1 | /ask | Direct prompt injection | LLM01 | Regex filter, length cap, `<untrusted>` wrapping | Done |
| 2 | API | Cross-service access (BOLA) | API1, LLM02 | Per-user service RBAC, group ACL on retrieval | Done |
| 3 | Logs/metrics | Indirect injection in log lines | LLM01 | Untrusted wrapping, read-only tools, templates only | Done |
| 4 | Logs -> LLM | Secrets/PII to provider and audit | LLM02 | Redaction before prompt | Done (regex) |
| 5 | Ingest | Poisoned runbook | LLM04 | Injection scan quarantines chunks, content hash | Partial |
| 6 | Vector store | Cross-ACL retrieval | LLM08 | Hard ACL filter on every query | Done |
| 7 | Cache | Cross-user cached answers | LLM08 | Key includes ACL scope; only approved answers; TTL | Done |
| 8 | Investigator -> Verifier | Cascading hallucination | T5, LLM09 | Verifier checks raw evidence ids and citations | Done |
| 9 | Agent messages | Message poisoning | T12 | Typed Pydantic messages, deterministic citation check | Done |
| 10 | Agent loop | Infinite loop | T4, T6 | Max rounds, token budget | Done |
| 11 | Tools | Argument injection | LLM05 | Enum metrics, service allowlist, no shell/SQL | Done |
| 12 | Tools | Excessive agency | LLM06 | Read-only tools, scoped to user's services | Done |
| 13 | System prompt | Leakage | LLM07 | No secrets in prompts | Partial |
| 14 | Diagnosis | Confident wrong RCA | LLM09 | Citations required, confidence cap, "inconclusive" | Done |
| 15 | Cost | Denial of wallet | LLM10 | Rate limit, token budget, max_tokens, model cascade, trimmed prompts | Done |
| 16 | Supply chain | Malicious model/deps | LLM03 | Pin hashes, safetensors only | Design |
| 17 | Audit | Repudiation | T8 | Hash-chained append-only log | Done |
| 18 | Human on-call | Approval fatigue | T10, T15 | Severity grouping, show uncertainty | Design |
| 19 | LLM provider | Data retention | LLM02 | Synthetic data in POC; ZDR/region in prod | Design |
