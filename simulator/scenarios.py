"""Deterministic synthetic incidents: metrics, logs and deploys with known ground truth."""
import random
from dataclasses import dataclass, field

MINUTES = 60
ONSET = 40


@dataclass
class Scenario:
    id: str
    service: str
    category: str
    root_cause: str
    runbook_id: str
    metrics: dict[str, list[float]] = field(default_factory=dict)
    logs: list[dict] = field(default_factory=list)
    deploys: list[dict] = field(default_factory=list)


def _series(rng, base, noise, after=None, shift=None):
    out = []
    for m in range(MINUTES):
        v = base + rng.uniform(-noise, noise)
        if after is not None and m >= after:
            v = shift(m, v)
        out.append(round(v, 3))
    return out


def _noise_logs(rng, service):
    return [{"minute": m, "level": "INFO", "service": service,
             "message": f"request handled path=/v1/items id={rng.randint(1000, 9999)} ms={rng.randint(20, 90)}"}
            for m in range(0, MINUTES, 3)]


def _db_pool(seed=1):
    rng = random.Random(seed)
    s = Scenario("db_pool_exhaustion", "payments-service", "db_pool_exhaustion",
                 "Connection pool to postgres is exhausted (active=max_pool), requests time out",
                 "rb-payments-db-pool")
    s.metrics = {
        "latency_p95_ms": _series(rng, 180, 20, ONSET, lambda m, v: v + 2500 + (m - ONSET) * 40),
        "error_rate": _series(rng, 0.004, 0.002, ONSET, lambda m, v: 0.18 + rng.uniform(0, 0.05)),
        "db_active_connections": _series(rng, 22, 4, ONSET, lambda m, v: 50.0),
        "cpu_pct": _series(rng, 35, 5),
    }
    s.logs = _noise_logs(rng, s.service)
    for m in range(ONSET, MINUTES):
        s.logs.append({"minute": m, "level": "ERROR", "service": s.service,
                       "message": f"HikariPool-1 - Connection is not available, request timed out after 30000ms txid={rng.randint(10**5, 10**6)}"})
        s.logs.append({"minute": m, "level": "WARN", "service": s.service,
                       "message": "connection pool exhausted active=50 max=50 waiting=%d" % rng.randint(10, 80)})
    s.deploys = [{"id": "dep-payments-3.8.1", "service": s.service, "minute": 5,
                  "description": "payments-service 3.8.1: update logging format"}]
    return s


def _bad_deploy(seed=2):
    rng = random.Random(seed)
    s = Scenario("bad_deploy", "orders-service", "bad_deploy",
                 "Deploy orders-service v2.14.0 introduced a NullPointerException in PricingEngine",
                 "rb-bad-deploy-rollback")
    s.metrics = {
        "latency_p95_ms": _series(rng, 220, 25, ONSET - 2, lambda m, v: v + 400),
        "error_rate": _series(rng, 0.003, 0.002, ONSET - 2, lambda m, v: 0.35 + rng.uniform(0, 0.05)),
        "db_active_connections": _series(rng, 18, 3),
        "cpu_pct": _series(rng, 40, 5),
    }
    s.logs = _noise_logs(rng, s.service)
    for m in range(ONSET - 2, MINUTES):
        s.logs.append({"minute": m, "level": "ERROR", "service": s.service,
                       "message": f"NullPointerException in PricingEngine.compute order_id={rng.randint(10**4, 10**5)}"})
    s.deploys = [{"id": "dep-orders-2.14.0", "service": s.service, "minute": ONSET - 3,
                  "description": "orders-service v2.14.0: enable new pricing engine"}]
    return s


def _tls_expiry(seed=3):
    rng = random.Random(seed)
    s = Scenario("tls_expiry", "auth-service", "tls_expiry",
                 "TLS certificate of upstream idp.internal expired, handshakes fail",
                 "rb-tls-cert-expiry")
    s.metrics = {
        "latency_p95_ms": _series(rng, 120, 15, ONSET, lambda m, v: v + 150),
        "error_rate": _series(rng, 0.002, 0.001, ONSET, lambda m, v: 0.6),
        "db_active_connections": _series(rng, 10, 2),
        "cpu_pct": _series(rng, 20, 3),
    }
    s.logs = _noise_logs(rng, s.service)
    for m in range(ONSET, MINUTES):
        s.logs.append({"minute": m, "level": "ERROR", "service": s.service,
                       "message": "SSL handshake failed: certificate has expired for host idp.internal:443"})
    s.deploys = []
    return s


_BUILDERS = {"db_pool_exhaustion": _db_pool, "bad_deploy": _bad_deploy, "tls_expiry": _tls_expiry}


def scenario_ids() -> list[str]:
    return list(_BUILDERS)


def build(scenario_id: str) -> Scenario:
    if scenario_id not in _BUILDERS:
        raise KeyError(scenario_id)
    return _BUILDERS[scenario_id]()
