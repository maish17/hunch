"""Append-only event log (runs/<run_id>/events.jsonl).

Responsibility: record every anomaly, prediction, work order, status change, standby
choice and garage action as one JSON line (schemas/event_log_entry.schema.json),
with refs linking each decision to what caused it. Opened in append mode only;
nothing ever rewrites or deletes a line. Later missions (accuracy reports,
explanations) are built by reading this file, so put the full contract object in
payload whenever there is one.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from schemas.validate import validate


class EventLog:
    """Writes events.jsonl for one run."""

    def __init__(self, path: Path, start_time_utc: str) -> None:
        """Remember where to write. If the file already has lines, numbering continues
        after them (the file is never truncated here; the pipeline deletes old runs)."""
        self.path = Path(path)
        self.start = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.next_number = len(self.read_all()) + 1

    def append(self, event_type: str, t_s: int, robot_id: str | None, summary: str,
               payload: dict, refs: dict | None = None) -> dict:
        """Build the entry (event_id EV-000001 style), validate it, append one line, return it."""
        entry = {
            "schema_version": "1.0.0",
            "event_id": f"EV-{self.next_number:06d}",
            "t_s": t_s,
            "at": (self.start + timedelta(seconds=t_s)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": event_type,
            "robot_id": robot_id,
            "refs": refs or {},
            "summary": summary,
            "payload": payload,
        }
        validate(entry, "event_log_entry")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        self.next_number += 1
        return entry

    def read_all(self) -> list[dict]:
        """Every entry so far, oldest first (used by the alerts feed)."""
        if not self.path.exists():
            return []
        entries = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        return entries
