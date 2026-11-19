---
document_id: rb-payments-db-pool@1.4
document: "Runbook: Connection pool exhaustion (obsolete)"
doc_type: runbook
service: payments-service
category: db_pool_exhaustion
version: "1.4"
status: superseded
owner: team-payments
updated_at: "2025-02-01"
source: git://runbooks/payments/db-pool-v1.4.md
acl: [payments-oncall, sre]
---
# Connection pool exhaustion

## Mitigation
Restart the postgres instance to release all pool connections.
