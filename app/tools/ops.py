"""Read-only operational tools over the simulated environment."""
import re
import statistics
from collections import Counter

from app import config
from simulator.scenarios import ONSET, Scenario

METRICS = {"latency_p95_ms", "error_rate", "db_active_connections", "cpu_pct"}

_MASKS = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f-]{27}\b"), "<*>"),
    (re.compile(r"\b\d+(?:\.\d+)?\b"), "<*>"),
]


def _check_service(env: Scenario, service: str, allowed: list[str]) -> None:
    if service not in config.SERVICE_GRAPH or service not in allowed:
        raise PermissionError(f"service not allowed: {service}")


def query_metrics(env: Scenario, service: str, metric: str, allowed: list[str]) -> dict:
    _check_service(env, service, allowed)
    if metric not in METRICS:
        raise ValueError(f"unknown metric: {metric}")
    series = env.metrics[metric]
    base, recent = series[: ONSET - 10], series[-10:]
    mu = statistics.mean(base)
    sd = statistics.pstdev(base) or 1e-9
    z = (statistics.mean(recent) - mu) / sd
    first = next((i for i, v in enumerate(series) if abs(v - mu) > 4 * sd), None)
    return {"metric": metric, "baseline": round(mu, 4), "recent": round(statistics.mean(recent), 4),
            "zscore": round(z, 1), "anomalous": abs(z) > 4, "onset_minute": first}


def search_logs(env: Scenario, service: str, allowed: list[str], level: str | None = None,
                top: int = 5) -> list[dict]:
    _check_service(env, service, allowed)
    counts: Counter[str] = Counter()
    for line in env.logs:
        if line["service"] != service or (level and line["level"] != level):
            continue
        if line["level"] == "INFO":
            continue
        counts[template(line["message"])] += 1
    return [{"template": t, "count": c} for t, c in counts.most_common(top)]


def template(message: str) -> str:
    for pat, rep in _MASKS:
        message = pat.sub(rep, message)
    return message


def recent_deploys(env: Scenario, service: str, allowed: list[str], window_min: int = 30) -> list[dict]:
    _check_service(env, service, allowed)
    return [d for d in env.deploys if d["service"] == service and 0 <= ONSET - d["minute"] <= window_min]
