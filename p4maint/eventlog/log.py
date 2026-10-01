"""Append-only event log (runs/<run_id>/events.jsonl).

Responsibility: record every anomaly, prediction, work order, status change, standby
choice and garage action as one JSON line (schemas/event_log_entry.schema.json),
with refs linking each decision to what caused it. Opened in append mode only;
nothing ever rewrites or deletes a line. Later missions (accuracy reports,
explanations) are built by reading this file, so put the full contract object in
payload whenever there is one.

STATUS: stubs.
"""

from pathlib import Path


class EventLog:
    """Writes events.jsonl for one run."""

    def __init__(self, path: Path, start_time_utc: str) -> None:
        """TODO: remember path and start time; self.next_number = 1; create the parent
        folder. Do NOT truncate an existing file here - the pipeline deletes old runs."""
        raise NotImplementedError("EventLog.__init__")

    def append(self, event_type: str, t_s: int, robot_id: str | None, summary: str,
               payload: dict, refs: dict | None = None) -> dict:
        """Build the entry (event_id EV-000001 style), validate it, append one line, return it."""
        raise NotImplementedError("EventLog.append")

    def read_all(self) -> list[dict]:
        """Every entry so far, oldest first (used by the alerts feed)."""
        raise NotImplementedError("EventLog.read_all")
