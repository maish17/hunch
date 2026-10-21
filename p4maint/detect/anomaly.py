"""Anomaly detection: raise an alert, automatically, when a channel goes bad (Mission 2).

Responsibility: watch the per-sample statuses from health.evaluate and emit an
anomaly_event (schemas/anomaly_event.schema.json) when a channel has been WARNING
or CRITICAL for long enough to be real. Each event names the robot, channel,
component, subsystem, start time, severity and magnitude.

False positives waste P5 capacity, so (all numbers from detector.json "anomaly"):
  - persistence: raise only after persistence_samples consecutive bad samples;
    t_s of the event is the FIRST bad sample, detected_t_s is the end of the batch
  - escalation: WARNING -> CRITICAL on the same channel raises a new event
  - suppression: no repeat of the same robot+channel+severity within realert_suppress_s
  - clearing: after clear_after_samples consecutive NORMAL samples the anomaly is
    reported as cleared and the channel is re-armed
"""

import math
from datetime import datetime, timedelta

import pandas as pd

from schemas.validate import validate

BAD = ("WARNING", "CRITICAL")


class AnomalyDetector:
    """Keeps per-(robot, channel) counters between batches."""

    def __init__(self, detector_cfg: dict, channels_cfg: dict, start_time_utc: str) -> None:
        settings = detector_cfg["anomaly"]
        self.persistence = settings["persistence_samples"]
        self.clear_after = settings["clear_after_samples"]
        self.suppress_s = settings["realert_suppress_s"]
        self.channels = {channel["name"]: channel for channel in channels_cfg["channels"]}
        self.start_time_utc = start_time_utc
        self.next_number = 1
        self.tracks: dict[tuple[str, str], dict] = {}

    def _track(self, robot_id: str, channel: str) -> dict:
        key = (robot_id, channel)
        if key not in self.tracks:
            self.tracks[key] = {
                "bad_run": 0, "bad_start": None,        # consecutive WARNING-or-worse samples
                "critical_run": 0, "critical_start": None,
                "normal_run": 0,
                "active": None,                          # the open anomaly event, if any
                "last_alert_t_s": {},                    # severity -> t_s it was last raised
            }
        return self.tracks[key]

    def _raise(self, robot_id: str, track: dict, first_bad: dict, severity: str, now_t_s: int) -> dict | None:
        """Open an anomaly at this severity; return the event unless it is suppressed."""
        last = track["last_alert_t_s"].get(severity)
        track["last_alert_t_s"][severity] = first_bad["t_s"]
        if last is not None and first_bad["t_s"] - last < self.suppress_s:
            track["active"] = {"severity": severity, "anomaly_id": None, "suppressed": True}
            return None
        anomaly_id = f"AN-{self.next_number:06d}"
        self.next_number += 1
        event = make_anomaly_event(anomaly_id, robot_id, first_bad, now_t_s,
                                   self.channels[first_bad["channel"]], severity, self.start_time_utc)
        track["active"] = event
        return event

    def update(self, evaluated: pd.DataFrame, robot_id: str, now_t_s: int) -> tuple[list[dict], list[dict]]:
        """Process one robot's evaluated batch (output of health.evaluate.evaluate_samples).

        Returns (raised, cleared): new anomaly_event dicts, and small dicts
        {"robot_id", "channel", "anomaly_id", "severity", "t_s"} for anomalies that just cleared.
        """
        raised, cleared = [], []
        ordered = evaluated.sort_values(["channel", "t_s"])
        fields = ["t_s", "op_mode", "channel", "value", "baseline", "deviation", "status", "rule"]
        for channel, rows in ordered.groupby("channel", sort=False):
            track = self._track(robot_id, channel)
            columns = {field: rows[field].tolist() for field in fields}
            for i, status in enumerate(columns["status"]):
                row = {field: columns[field][i] for field in fields} if status != "NORMAL" or track["active"] else None
                if status in BAD:
                    track["normal_run"] = 0
                    if track["bad_run"] == 0:
                        track["bad_start"] = row
                    track["bad_run"] += 1
                    if status == "CRITICAL":
                        if track["critical_run"] == 0:
                            track["critical_start"] = row
                        track["critical_run"] += 1
                    else:
                        track["critical_run"] = 0

                    active = track["active"]
                    if active is None and track["bad_run"] >= self.persistence:
                        if track["critical_run"] >= self.persistence:
                            event = self._raise(robot_id, track, track["critical_start"], "CRITICAL", now_t_s)
                        else:
                            event = self._raise(robot_id, track, track["bad_start"], "WARNING", now_t_s)
                        if event:
                            raised.append(event)
                    elif active is not None and active["severity"] == "WARNING" and track["critical_run"] >= self.persistence:
                        event = self._raise(robot_id, track, track["critical_start"], "CRITICAL", now_t_s)
                        if event:
                            raised.append(event)
                elif status == "NORMAL":
                    track["bad_run"] = track["critical_run"] = 0
                    if track["active"] is not None:
                        track["normal_run"] += 1
                        if track["normal_run"] >= self.clear_after:
                            active = track["active"]
                            if active.get("anomaly_id"):
                                cleared.append({"robot_id": robot_id, "channel": channel, "anomaly_id": active["anomaly_id"],
                                                "severity": active["severity"], "t_s": int(row["t_s"])})
                            track["active"] = None
                            track["normal_run"] = 0
                else:  # UNKNOWN: no data, so neither confirms nor clears anything
                    track["bad_run"] = track["critical_run"] = 0
        raised.sort(key=lambda event: (event["t_s"], event["anomaly_id"]))
        return raised, cleared

    def active_anomalies(self, robot_id: str) -> list[dict]:
        """Anomaly events for this robot that have not cleared yet (used by diagnosis)."""
        events = []
        for (track_robot, _channel), track in self.tracks.items():
            active = track["active"]
            if track_robot == robot_id and active is not None and active.get("anomaly_id"):
                events.append(active)
        return sorted(events, key=lambda event: event["t_s"])


def _limit_for_rule(channel_cfg: dict, rule: str) -> float:
    """The number behind a rule name, e.g. RELATIVE_WARNING_HIGH -> limits.warning_high."""
    kind, level, side = rule.split("_")
    key = f"{level.lower()}_{side.lower()}"
    if kind == "HARD":
        return channel_cfg["hard_limits"][key]
    return channel_cfg["limits"][key]


def _message(robot_id: str, channel_cfg: dict, row: dict, severity: str, limit: float) -> str:
    label = channel_cfg["label"][0].lower() + channel_cfg["label"][1:]
    units = channel_cfg["units"]
    rule = row["rule"]
    if rule.startswith("RELATIVE") and row["deviation"] is not None:
        direction = "above" if row["deviation"] > 0 else "below"
        return f"{robot_id} {label} is {abs(row['deviation']):.2f} {units} {direction} its {row['op_mode']} baseline"
    if rule.startswith("HARD"):
        return f"{robot_id} {label} is {row['value']:.2f} {units}, past its hard limit of {limit} {units}"
    return f"{robot_id} {label} is {row['value']:.2f} {units}, past its {severity} limit of {limit} {units}"


def make_anomaly_event(anomaly_id: str, robot_id: str, first_bad: dict, detected_t_s: int,
                       channel_cfg: dict, severity: str, start_time_utc: str) -> dict:
    """Build and validate one anomaly_event dict.

    first_bad is the row of the evaluated table where the condition began (as a dict).
    """
    t_s = int(first_bad["t_s"])
    limit = _limit_for_rule(channel_cfg, first_bad["rule"])
    baseline = first_bad["baseline"]
    if baseline is not None and isinstance(baseline, float) and math.isnan(baseline):
        baseline = None
    start = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ")
    event = {
        "schema_version": "1.0.0",
        "anomaly_id": anomaly_id,
        "robot_id": robot_id,
        "t_s": t_s,
        "timestamp": (start + timedelta(seconds=t_s)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "detected_t_s": int(detected_t_s),
        "channel": channel_cfg["name"],
        "component": channel_cfg["component"],
        "subsystem": channel_cfg["subsystem"],
        "op_mode": first_bad["op_mode"],
        "severity": severity,
        "value": round(float(first_bad["value"]), 4),
        "baseline": None if baseline is None else round(float(baseline), 4),
        "magnitude": None if baseline is None else round(float(first_bad["value"]) - float(baseline), 4),
        "limit": limit,
        "rule": first_bad["rule"],
        "units": channel_cfg["units"],
        "message": _message(robot_id, channel_cfg, first_bad, severity, limit),
    }
    validate(event, "anomaly_event")
    return event
