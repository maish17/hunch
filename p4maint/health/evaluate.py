"""Health evaluation: every reading -> NORMAL / WARNING / CRITICAL (Mission 1).

Responsibility: compare each smoothed reading with its baseline for the robot's
CURRENT operating mode, using only the limits in config/channels.json, and roll the
result up COMPONENT -> SUBSYSTEM -> ROBOT (worst status wins). Output is the
health_snapshot contract plus a long table of per-sample statuses that the anomaly
detector consumes.

Baseline types (config/channels.json baseline_type; details in config/modes.json):
    per_mode       constant for the current mode
    thermal_lag    mode steady-state, approached through a first-order lag (tau from detector.json)
    battery_model  V_oc(SOC) - I * R_nominal (detector.json battery_model)
    none           no baseline; absolute limits only

Status rule, in order: hard limit crossed -> CRITICAL; critical limit crossed ->
CRITICAL; warning limit crossed -> WARNING; else NORMAL. A missing value -> UNKNOWN.
Relative per_mode checks are skipped for detector.json mode_change_grace_s after a
mode change; hard limits never are.

STATUS: stubs. This is Mission 1 logic for the team to write.
"""

import pandas as pd


def new_baseline_state() -> dict:
    """Per-robot memory the lagged baselines need between batches.

    Suggested shape: {robot_id: {"thermal": {channel: lagged_baseline}, "last_mode": str,
    "mode_since_t_s": int}}.
    """
    raise NotImplementedError("new_baseline_state")


def baseline_value(channel_cfg: dict, op_mode: str, sample: pd.Series, robot_state: dict,
                   modes_cfg: dict, detector_cfg: dict) -> float | None:
    """Expected value of one channel for one sample, or None for baseline_type 'none'.

    TODO(Mission 1): branch on channel_cfg["baseline_type"]. For thermal_lag, step the
    lagged value stored in robot_state toward the mode's steady state:
        lagged += (target - lagged) * (1 - exp(-dt / tau_s))
    For battery_model use the sample's battery_soc_pct and battery_current_a.
    """
    raise NotImplementedError("baseline_value")


def absolute_limits(channel_cfg: dict, baseline: float | None) -> dict[str, float | None]:
    """The channel's four limit lines as absolute values for this baseline.

    Returns {"warning_low", "warning_high", "critical_low", "critical_high"}; None where a
    line does not apply. Relative limits are baseline + offset; absolute limits are
    used as-is; hard limits tighten the critical lines. The dashboard export uses this
    same function for the limit bands, so the plots always match the evaluation.
    """
    raise NotImplementedError("absolute_limits")


def classify(value: float | None, channel_cfg: dict, baseline: float | None) -> tuple[str, str | None]:
    """(status, rule) for one value, e.g. ("WARNING", "RELATIVE_WARNING_HIGH").

    rule names are the enum in schemas/health_snapshot.schema.json; None when NORMAL.
    """
    raise NotImplementedError("classify")


def evaluate_samples(batch_df: pd.DataFrame, robot_id: str, channels_cfg: dict, modes_cfg: dict,
                     detector_cfg: dict, baseline_state: dict) -> pd.DataFrame:
    """Status of every channel at every sample of one robot's batch.

    Returns a long table, one row per (t_s, channel), with columns:
    t_s, op_mode, channel, value (smoothed), baseline, deviation, status, rule.

    TODO(Mission 1): smooth each channel with a rolling median over
    detector_cfg["evaluation"]["smoothing_window_s"], then baseline_value() and classify().
    """
    raise NotImplementedError("evaluate_samples")


def rollup(statuses: list[str]) -> str:
    """Worst status in the list (CRITICAL > WARNING > UNKNOWN > NORMAL). Empty -> NORMAL."""
    raise NotImplementedError("rollup")


def health_score(subsystem_statuses: dict[str, str], detector_cfg: dict) -> int | None:
    """0-100 score from detector.json health_score (placeholder rule: minimum of
    status_points over subsystems). None if every subsystem is UNKNOWN."""
    raise NotImplementedError("health_score")


def build_snapshot(evaluated: pd.DataFrame, robot_id: str, channels_cfg: dict, detector_cfg: dict,
                   start_time_utc: str) -> dict:
    """health_snapshot contract for the LAST sample in `evaluated`.

    TODO(Mission 1): walk config/channels.json hierarchy (subsystems -> components ->
    channels), fill each channel entry from the last t_s, roll statuses up with rollup(),
    then validate with schemas.validate.validate(snapshot, "health_snapshot").
    """
    raise NotImplementedError("build_snapshot")
