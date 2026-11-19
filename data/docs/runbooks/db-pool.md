---
document_id: rb-payments-db-pool
document: "Runbook: Connection pool exhaustion"
doc_type: runbook
service: payments-service
category: db_pool_exhaustion
version: "2.3"
status: current
replaces: rb-payments-db-pool@1.4
related_to: [pm-2026-031, svc-payments-overview]
owner: team-payments
updated_at: "2026-09-10"
source: git://runbooks/payments/db-pool.md
acl: [payments-oncall, sre]
---
# Connection pool exhaustion

## Diagnosis
Alert on p95 latency and error rate in payments-service. Check that db_active_connections is at the pool maximum (50) and that logs show "Connection is not available" or "connection pool exhausted".

## Mitigation
Immediate step: temporarily raise max_pool to 80 with the runtime flag `db.pool.max` and scale out payments-service replicas. Do not restart postgres. Find slow queries with pg_stat_activity and cancel those running longer than 60s.

## Prevention
Add an alert on db_active_connections above 80% of the pool and review transactions that do not release connections.
