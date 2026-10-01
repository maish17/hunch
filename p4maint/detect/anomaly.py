"""Anomaly detection: raise an alert, automatically, when a channel goes bad (Mission 2).

Responsibility: watch the per-sample statuses from health.evaluate and emit an
anomaly_event (schemas/anomaly_event.schema.json) when a channel has been WARNING
or CRITICAL for long enough to be real. Each event names the robot, channel,
component, subsystem, start time, severity and magnitude.

False positives waste P5 capacity, so (all numbers from detector.json "anomaly"):
  - persistence: raise only after persistence_samples consecutive bad samples;
    t_s of the event is the FIRST bad sample, detected_t_s is now
  - escalation: WARNING -> CRITICAL on the same channel raises a new event
  - suppression: no repeat of the same robot+channel+severity within realert_suppress_s
  - clearing: after clear_after_samples consecutive NORMAL samples, emit ANOMALY_CLEARED
    to the event log and re-arm the channel

STATUS: stubs. This is Mission 2 logic for the team to write.
"""

import pandas as pd


class AnomalyDetector:
    """Keeps per-(robot, channel) counters between batches."""

    def __init__(self, detector_cfg: dict, channels_cfg: dict, start_time_utc: str) -> None:
        """TODO(Mission 2): store configs; self.next_number = 1; empty counter dicts."""
        raise NotImplementedError("AnomalyDetector.__init__")

    def update(self, evaluated: pd.DataFrame, robot_id: str, now_t_s: int) -> tuple[list[dict], list[dict]]:
        """Process one robot's evaluated batch (output of health.evaluate.evaluate_samples).

        Returns (raised, cleared): new anomaly_event dicts, and small dicts
        {"robot_id", "channel", "anomaly_id", "t_s"} for anomalies that just cleared.
        """
        raise NotImplementedError("AnomalyDetector.update")

    def active_anomalies(self, robot_id: str) -> list[dict]:
        """Anomaly events for this robot that have not cleared yet (used by diagnosis)."""
        raise NotImplementedError("AnomalyDetector.active_anomalies")


def make_anomaly_event(anomaly_id: str, robot_id: str, first_bad: pd.Series, detected_t_s: int,
                       channel_cfg: dict, severity: str, start_time_utc: str) -> dict:
    """Build and validate one anomaly_event dict.

    first_bad is the row of the evaluated table where the condition began. message is
    one plain sentence, e.g. "P2-02 front-left drive temperature is 15.4 degC above its
    TRAVERSE_EMPTY baseline".
    """
    raise NotImplementedError("make_anomaly_event")
