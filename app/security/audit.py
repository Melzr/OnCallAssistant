import hashlib
import json
import threading
import time
from pathlib import Path

from app import config

_lock = threading.Lock()


class AuditLog:
    """Append-only JSONL with a hash chain so edits are detectable."""

    def __init__(self, path: Path | None = None):
        self.path = path or config.VAR_DIR / "audit.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        last = ""
        with self.path.open() as f:
            for line in f:
                last = line
        return json.loads(last)["hash"] if last else "0" * 64

    def write(self, incident_id: str, event: str, user: str, data: dict) -> None:
        with _lock:
            rec = {"ts": time.time(), "incident_id": incident_id, "event": event, "user": user, "data": data,
                   "prev": self._last_hash()}
            rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()
            with self.path.open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")

    def read(self, incident_id: str) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open() as f:
            return [r for r in map(json.loads, f) if r["incident_id"] == incident_id]

    def verify(self) -> bool:
        prev = "0" * 64
        if not self.path.exists():
            return True
        with self.path.open() as f:
            for line in f:
                rec = json.loads(line)
                h = rec.pop("hash")
                if rec["prev"] != prev or hashlib.sha256(
                        json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest() != h:
                    return False
                prev = h
        return True
