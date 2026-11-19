---
document_id: rb-tls-cert-expiry
document: "Runbook: Expired TLS certificate"
doc_type: runbook
service: auth-service
category: tls_expiry
version: "1.0"
status: current
owner: team-identity
updated_at: "2026-06-15"
source: git://runbooks/auth/tls-expiry.md
acl: [sre, orders-oncall, payments-oncall]
---
# Expired TLS certificate

## Diagnosis
"SSL handshake failed: certificate has expired" errors in the service consuming an upstream. Check the expiry date with `openssl s_client`.

## Mitigation
Immediate step: renew the upstream certificate and reload the trust store. Never disable TLS verification as a workaround.
