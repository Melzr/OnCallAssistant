---
document_id: rb-bad-deploy-rollback
document: "Runbook: Bad deploy and rollback"
doc_type: runbook
service: orders-service
category: bad_deploy
version: "1.2"
status: current
related_to: [svc-orders-overview]
owner: team-orders
updated_at: "2026-08-02"
source: git://runbooks/orders/bad-deploy.md
acl: [orders-oncall, sre]
---
# Bad deploy

## Diagnosis
Sudden error rate increase coinciding with a recent deploy (under 30 minutes). Logs show new exceptions, for example NullPointerException, that did not exist before.

## Mitigation
Immediate step: roll back to the previous version with `deploy rollback orders-service`. Confirm the error rate returns to baseline and open a ticket for the change author.
