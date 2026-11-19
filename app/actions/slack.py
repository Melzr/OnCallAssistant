import re

import httpx

from app import config
from app.schemas import FinalAnswer

_LINK = re.compile(r"https?://([^/\s>|]+)\S*")


def escape_mrkdwn(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def strip_unlisted_links(text: str) -> str:
    return _LINK.sub(lambda m: m.group(0) if m.group(1) in config.LINK_DOMAIN_ALLOWLIST else "[link removed]", text)


def format_message(a: FinalAnswer) -> str:
    body = (
        f"*Incident {a.incident_id}* | {a.service} | status: {a.status} | confidence: {a.confidence:.2f}\n"
        f"*Probable cause:* {a.root_cause}\n"
        f"*Suggested mitigation (needs human approval):* {a.mitigation_text or 'n/a'}\n"
        f"*Sources:* {', '.join(a.citations) or 'none'}"
    )
    return strip_unlisted_links(escape_mrkdwn(body))


def post(answer: FinalAnswer, channel: str = "#incidents") -> dict:
    if channel not in config.SLACK_CHANNEL_ALLOWLIST:
        raise PermissionError(f"channel not allowed: {channel}")
    text = format_message(answer)
    url = config.slack_webhook()
    if not url:
        out = config.VAR_DIR / "slack_outbox.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a") as f:
            f.write(f"{channel}\t{text}\n---\n")
        return {"sent": False, "outbox": str(out)}
    r = httpx.post(url, json={"channel": channel, "text": text}, timeout=10)
    r.raise_for_status()
    return {"sent": True}
