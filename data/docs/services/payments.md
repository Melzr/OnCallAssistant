---
document_id: svc-payments-overview
document: "Service: payments-service"
doc_type: service
service: payments-service
version: "1.0"
status: current
owner: team-payments
updated_at: "2026-07-01"
source: git://docs/services/payments.md
acl: [payments-oncall, sre]
---
# payments-service

## Architecture
Processes payments and depends on postgres through a connection pool with a maximum size of 50 (db.pool.max). SLO: p95 under 500ms and error rate under 1%.
