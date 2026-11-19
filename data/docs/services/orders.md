---
document_id: svc-orders-overview
document: "Service: orders-service"
doc_type: service
service: orders-service
version: "1.0"
status: current
owner: team-orders
updated_at: "2026-07-01"
source: git://docs/services/orders.md
acl: [orders-oncall, sre]
---
# orders-service

## Architecture
Manages orders and computes prices with PricingEngine. Depends on payments-service and postgres. Deployed several times a week with automated rollback available.
