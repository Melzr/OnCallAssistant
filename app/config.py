import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "data" / "docs"
VAR_DIR = ROOT / "var"


def load_env(path: Path) -> None:
    """Loads KEY=VALUE lines into os.environ without overriding variables already set."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            os.environ.setdefault(key.strip(), value)


load_env(ROOT / ".env")

MODEL_TRIAGE = "claude-haiku-5-5"
MODEL_INVESTIGATOR = "claude-sonnet-5-5"
MODEL_INVESTIGATOR_ESCALATION = "claude-opus-5-5"
MODEL_VERIFIER = "claude-sonnet-5-5"
MODEL_RESPONDER = "claude-haiku-5-5"

MAX_VERIFY_ROUNDS = 2
MAX_QUESTION_CHARS = 1500
MAX_PROMPT_DOCS = 4
MAX_DOC_CHARS = 1200
TOKEN_BUDGET_PER_INCIDENT = 60_000
CACHE_TTL_SECONDS = 600
RATE_LIMIT_PER_MINUTE = 20

SERVICE_GRAPH = {
    "api-gateway": ["auth-service", "orders-service"],
    "orders-service": ["payments-service", "postgres"],
    "payments-service": ["postgres"],
    "auth-service": [],
    "postgres": [],
}

# Static users for the POC. Production would use JWT from an IdP.
USERS = {
    "key-alice-sre": {"name": "alice", "role": "admin", "groups": ["sre", "payments-oncall", "orders-oncall"],
                      "services": list(SERVICE_GRAPH)},
    "key-bob-orders": {"name": "bob", "role": "oncall", "groups": ["orders-oncall"],
                       "services": ["orders-service", "api-gateway"]},
}


def anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def anthropic_base_url() -> str | None:
    return os.environ.get("ANTHROPIC_BASE_URL") or None


def anthropic_headers() -> dict[str, str]:
    """Parses ANTHROPIC_CUSTOM_HEADERS ('Name: value' per line)."""
    out = {}
    for line in os.environ.get("ANTHROPIC_CUSTOM_HEADERS", "").splitlines():
        name, sep, value = line.partition(":")
        if sep and name.strip():
            out[name.strip()] = value.strip()
    return out
