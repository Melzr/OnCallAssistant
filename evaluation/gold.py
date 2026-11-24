"""Labelled data for evaluation: retrieval queries and the ground truth of each scenario."""

SRE = ["sre"]

RETRIEVAL = [
    {"q": "payments connection pool exhausted requests time out", "service": "payments-service",
     "intent": "diagnosis", "groups": SRE,
     "relevant": {"rb-payments-db-pool#diagnosis", "pm-2026-031#root-cause"}},
    {"q": "how to mitigate payments database pool exhaustion", "service": "payments-service",
     "intent": "mitigation", "groups": SRE, "relevant": {"rb-payments-db-pool#mitigation"}},
    {"q": "payments pool sizing and prevention", "service": "payments-service",
     "intent": "diagnosis", "groups": SRE, "relevant": {"rb-payments-db-pool#prevention"}},
    {"q": "el pool de conexiones de payments esta agotado", "service": "payments-service",
     "intent": "diagnosis", "groups": SRE,
     "relevant": {"rb-payments-db-pool#diagnosis", "pm-2026-031#root-cause"}},
    {"q": "orders error rate jumped after release NullPointerException", "service": "orders-service",
     "intent": "diagnosis", "groups": SRE, "relevant": {"rb-bad-deploy-rollback#diagnosis"}},
    {"q": "rollback orders-service bad deploy", "service": "orders-service",
     "intent": "mitigation", "groups": SRE, "relevant": {"rb-bad-deploy-rollback#mitigation"}},
    {"q": "auth-service SSL handshake failures certificate has expired", "service": "auth-service",
     "intent": "diagnosis", "groups": SRE, "relevant": {"rb-tls-cert-expiry#diagnosis"}},
    {"q": "renew certificate and reload trust store", "service": "auth-service",
     "intent": "mitigation", "groups": SRE, "relevant": {"rb-tls-cert-expiry#mitigation"}},
]

SCENARIOS = {
    "db_pool_exhaustion": {"category": "db_pool_exhaustion", "status": "approved",
                           "mitigation": "rb-payments-db-pool#mitigation",
                           "useful_docs": {"rb-payments-db-pool#diagnosis", "rb-payments-db-pool#mitigation",
                                           "pm-2026-031#root-cause"}},
    "bad_deploy": {"category": "bad_deploy", "status": "approved",
                   "mitigation": "rb-bad-deploy-rollback#mitigation",
                   "useful_docs": {"rb-bad-deploy-rollback#diagnosis", "rb-bad-deploy-rollback#mitigation"}},
    "tls_expiry": {"category": "tls_expiry", "status": "approved",
                   "mitigation": "rb-tls-cert-expiry#mitigation",
                   "useful_docs": {"rb-tls-cert-expiry#diagnosis", "rb-tls-cert-expiry#mitigation"}},
    "oom_killed": {"category": "unknown", "status": "inconclusive", "mitigation": None, "useful_docs": set()},
}
