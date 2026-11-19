import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "data" / "docs"
VAR_DIR = ROOT / "var"

MODEL_TRIAGE = "claude-haiku-5-5"
MODEL_INVESTIGATOR = "claude-opus-5-5"
MODEL_INVESTIGATOR_LOW = "claude-sonnet-5-5"
MODEL_VERIFIER = "claude-sonnet-5-5"
MODEL_RESPONDER = "claude-haiku-5-5"

MAX_VERIFY_ROUNDS = 2
MAX_QUESTION_CHARS = 1500
TOKEN_BUDGET_PER_INCIDENT = 60_000
CACHE_TTL_SECONDS = 600
RATE_LIMIT_PER_MINUTE = 20

SLACK_CHANNEL_ALLOWLIST = {"#incidents", "#oncall-copilot"}
LINK_DOMAIN_ALLOWLIST = {"runbooks.internal.example"}

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


def slack_webhook() -> str | None:
    return os.environ.get("SLACK_WEBHOOK_URL") or None


def alert_secret() -> str:
    return os.environ.get("ALERT_HMAC_SECRET", "change-me")
