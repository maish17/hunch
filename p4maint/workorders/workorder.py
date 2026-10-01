"""Work orders: the P4 -> P5 hand-off (Mission 5).

Responsibility: when a prediction (or a persistent CRITICAL anomaly) meets the
triggers in config/dispatch.json, create a self-contained work order containing
robot id, suspected failure, severity, predicted time-to-failure, recommended
action (from config/faults.json) and embedded telemetry evidence; validate it;
and save it to runs/<run_id>/work_orders/<id>.json.

Rules:
  - one open work order per robot; new evidence for a robot that already has one is
    logged, not turned into a second order
  - status only changes through set_status(), which checks
    config/state_machine.json work_order.transitions and appends to history
  - every write is validated against the schema first (the P5 side relies on it)

STATUS: stubs. This is Mission 5 logic for the team to write.
"""

from pathlib import Path

import pandas as pd


def new_work_order_id(created_utc: str, sequence: int) -> str:
    """WO-<YYYYMMDD>-<NNNN>, date from the creation timestamp, e.g. WO-20270301-0001."""
    raise NotImplementedError("new_work_order_id")


def should_create(prediction: dict | None, critical_anomalies: list[dict], robot: dict,
                  dispatch_cfg: dict) -> bool:
    """Apply config/dispatch.json work_order_triggers for one robot.

    False if the robot already has an open work order, or is IN_GARAGE / EN_ROUTE_P5.
    """
    raise NotImplementedError("should_create")


def embed_evidence(window_df: pd.DataFrame, channel_names: list[str], channels_cfg: dict,
                   op_mode: str, baselines: dict[str, float | None], dispatch_cfg: dict) -> list[dict]:
    """Evidence channel list for the work order: last work_order_evidence.window_s seconds,
    one point per downsample_s (minute means), with baseline and absolute WARNING /
    CRITICAL limits in the robot's current mode (use health.evaluate.absolute_limits)."""
    raise NotImplementedError("embed_evidence")


def create_work_order(work_order_id: str, prediction: dict, robot: dict, evidence_channels: list[dict],
                      summary: str, now_t_s: int, start_time_utc: str, faults_cfg: dict,
                      run_id: str) -> dict:
    """New work order in status OPEN with a one-entry history. Validated before return.

    robot is this robot's entry from the fleet_state contract. summary is a plain-language
    paragraph of what the evidence shows (see fixtures/contracts/work_order.example.json).
    """
    raise NotImplementedError("create_work_order")


def set_status(work_order: dict, new_status: str, now_t_s: int, start_time_utc: str, by: str,
               note: str, state_machine_cfg: dict) -> dict:
    """Move a work order to new_status, append to history, update updated_*.

    Raises p4maint.fleet.state_machine.IllegalTransition if the move is not listed in
    config/state_machine.json. Never edits earlier history entries.
    """
    raise NotImplementedError("set_status")


def save_work_order(work_order: dict, folder: Path) -> Path:
    """Validate, then write <folder>/<work_order_id>.json. Returns the path."""
    raise NotImplementedError("save_work_order")
