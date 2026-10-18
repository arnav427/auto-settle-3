import hashlib
import json
import time
from pathlib import Path


class AuditLog:
    """Append-only, hash-chained event log so tampering with past entries is detectable."""

    def __init__(self, claim_id: str, path: Path | None = None):
        self.claim_id = claim_id
        self.path = path
        self.entries: list[dict] = []
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, actor: str, event: str, data: dict | None = None) -> dict:
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        entry = {
            "seq": len(self.entries) + 1,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "actor": actor,
            "event": event,
            "data": data or {},
            "prev": prev,
        }
        entry["hash"] = self._digest(entry)
        self.entries.append(entry)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        return entry

    @staticmethod
    def _digest(entry: dict) -> str:
        body = {k: v for k, v in entry.items() if k != "hash"}
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    def verify(self) -> bool:
        prev = "0" * 64
        for e in self.entries:
            if e["prev"] != prev or e["hash"] != self._digest(e):
                return False
            prev = e["hash"]
        return True
