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

Smoothing: each channel is a rolling median over detector.json smoothing_window_s.
A single sensor dropout is filled by its neighbours; a channel with no data for the
whole window is UNKNOWN.
"""

import math
from datetime import datetime, timedelta

import pandas as pd

from schemas.validate import validate

STATUS_ORDER = {"NORMAL": 0, "UNKNOWN": 1, "WARNING": 2, "CRITICAL": 3}
LIMIT_KEYS = ["warning_low", "warning_high", "critical_low", "critical_high"]


def new_baseline_state() -> dict:
    """Per-robot memory the lagged baselines and the smoothing need between batches.

    One entry per robot, created on first use:
    {"thermal": {channel: lagged_baseline}, "last_mode": str, "mode_since_t_s": int,
     "last_t_s": int, "tail": DataFrame of the last few raw samples (for smoothing)}.
    """
    return {}


def _robot_state(baseline_state: dict, robot_id: str) -> dict:
    if robot_id not in baseline_state:
        baseline_state[robot_id] = {"thermal": {}, "last_mode": None, "mode_since_t_s": None,
                                    "last_t_s": None, "tail": None}
    return baseline_state[robot_id]


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def ocv_v(soc_pct: float, ocv_table: list[list[float]]) -> float:
    """Detector's own open-circuit-voltage curve: straight-line interpolation, clamped."""
    if soc_pct <= ocv_table[0][0]:
        return ocv_table[0][1]
    for (soc_lo, v_lo), (soc_hi, v_hi) in zip(ocv_table, ocv_table[1:]):
        if soc_pct <= soc_hi:
            return v_lo + (v_hi - v_lo) * (soc_pct - soc_lo) / (soc_hi - soc_lo)
    return ocv_table[-1][1]


def baseline_value(channel_cfg: dict, mode_baselines: dict, sample: dict, robot_state: dict,
                   detector_cfg: dict, dt_s: float) -> float | None:
    """Expected value of one channel for one sample, or None for baseline_type 'none'.

    mode_baselines is the current mode's "baselines" dict from config/modes.json.
    sample holds this instant's smoothed value of every channel. For thermal_lag, the
    lagged value kept in robot_state steps toward the mode's steady state:
        lagged += (target - lagged) * (1 - exp(-dt / tau_s))
    and starts at the first measured temperature.
    """
    kind = channel_cfg["baseline_type"]
    name = channel_cfg["name"]
    if kind == "none":
        return None
    if kind == "per_mode":
        return mode_baselines[name]
    if kind == "thermal_lag":
        target = mode_baselines[name]
        lagged = robot_state["thermal"].get(name)
        if lagged is None:
            lagged = target if _is_missing(sample[name]) else sample[name]
        else:
            tau_s = detector_cfg["thermal_model"]["tau_s"]
            lagged += (target - lagged) * (1 - math.exp(-dt_s / tau_s))
        robot_state["thermal"][name] = lagged
        return lagged
    if kind == "battery_model":
        soc, current = sample["battery_soc_pct"], sample["battery_current_a"]
        if _is_missing(soc) or _is_missing(current):
            return None
        model = detector_cfg["battery_model"]
        return ocv_v(soc, model["ocv_table_soc_pct_to_v"]) - current * model["r_int_nominal_ohm"]
    raise ValueError(f"Unknown baseline_type '{kind}' for {name}")


def absolute_limits(channel_cfg: dict, baseline: float | None) -> dict[str, float | None]:
    """The channel's four limit lines as absolute values for this baseline.

    Returns {"warning_low", "warning_high", "critical_low", "critical_high"}; None where a
    line does not apply. Relative limits are baseline + offset; absolute limits are
    used as-is; hard limits tighten the critical lines. The dashboard export uses this
    same function for the limit bands, so the plots always match the evaluation.
    """
    limits, hard = channel_cfg["limits"], channel_cfg["hard_limits"]
    lines = {}
    for key in LIMIT_KEYS:
        offset = limits[key]
        if offset is None:
            lines[key] = None
        elif limits["type"] == "absolute":
            lines[key] = offset
        elif baseline is None:
            lines[key] = None
        else:
            lines[key] = baseline + offset
    if hard["critical_high"] is not None:
        current = lines["critical_high"]
        lines["critical_high"] = hard["critical_high"] if current is None else min(current, hard["critical_high"])
    if hard["critical_low"] is not None:
        current = lines["critical_low"]
        lines["critical_low"] = hard["critical_low"] if current is None else max(current, hard["critical_low"])
    return lines


def classify(value: float | None, channel_cfg: dict, baseline: float | None,
             skip_relative: bool = False) -> tuple[str, str | None]:
    """(status, rule) for one value, e.g. ("WARNING", "RELATIVE_WARNING_HIGH").

    rule names are the enum in schemas/health_snapshot.schema.json; None when NORMAL.
    skip_relative (mode-change grace) ignores relative limits but never hard limits.
    """
    if _is_missing(value):
        return "UNKNOWN", "NO_DATA"
    hard = channel_cfg["hard_limits"]
    if hard["critical_high"] is not None and value >= hard["critical_high"]:
        return "CRITICAL", "HARD_CRITICAL_HIGH"
    if hard["critical_low"] is not None and value <= hard["critical_low"]:
        return "CRITICAL", "HARD_CRITICAL_LOW"

    limits = channel_cfg["limits"]
    if limits["type"] == "absolute":
        prefix, measured = "ABSOLUTE", value
    else:
        if skip_relative or baseline is None:
            return "NORMAL", None
        prefix, measured = "RELATIVE", value - baseline

    for level in ["critical", "warning"]:
        high, low = limits[f"{level}_high"], limits[f"{level}_low"]
        if high is not None and measured >= high:
            return level.upper(), f"{prefix}_{level.upper()}_HIGH"
        if low is not None and measured <= low:
            return level.upper(), f"{prefix}_{level.upper()}_LOW"
    return "NORMAL", None


def _smooth(rows: pd.DataFrame, names: list[str], window_samples: int, robot_state: dict) -> pd.DataFrame:
    """Rolling median per channel, continuing across batch boundaries."""
    frame = rows[names].reset_index(drop=True)
    tail = robot_state["tail"]
    if tail is not None:
        frame = pd.concat([tail, frame], ignore_index=True)
    smoothed = frame.rolling(window_samples, min_periods=1).median()
    robot_state["tail"] = frame.tail(max(window_samples - 1, 1)).reset_index(drop=True)
    return smoothed.tail(len(rows)).reset_index(drop=True)


def evaluate_samples(batch_df: pd.DataFrame, robot_id: str, channels_cfg: dict, modes_cfg: dict,
                     detector_cfg: dict, baseline_state: dict) -> pd.DataFrame:
    """Status of every channel at every sample of one robot's batch.

    Returns a long table, one row per (t_s, channel), with columns:
    t_s, op_mode, channel, value (smoothed), baseline, deviation, status, rule, in_grace.
    in_grace marks samples inside the mode-change grace period: their deviations are
    smoothing artefacts (the median lags the step), so trends and diagnosis skip them.
    """
    state = _robot_state(baseline_state, robot_id)
    rows = batch_df[batch_df["robot_id"] == robot_id].sort_values("t_s").reset_index(drop=True)
    channels = channels_cfg["channels"]
    names = [channel["name"] for channel in channels]
    window_samples = max(1, int(round(detector_cfg["evaluation"]["smoothing_window_s"])))
    smoothed = _smooth(rows, names, window_samples, state)
    columns = {name: smoothed[name].tolist() for name in names}
    mode_table = {mode["id"]: mode["baselines"] for mode in modes_cfg["modes"]}
    grace_s = detector_cfg["evaluation"]["mode_change_grace_s"]

    out = {"t_s": [], "op_mode": [], "channel": [], "value": [], "baseline": [],
           "deviation": [], "status": [], "rule": [], "in_grace": []}
    for i, (t_s, mode) in enumerate(zip(rows["t_s"].tolist(), rows["op_mode"].tolist())):
        if mode != state["last_mode"]:
            state["last_mode"] = mode
            state["mode_since_t_s"] = t_s
        dt_s = 1.0 if state["last_t_s"] is None else float(t_s - state["last_t_s"])
        state["last_t_s"] = t_s
        in_grace = t_s - state["mode_since_t_s"] < grace_s
        sample = {name: columns[name][i] for name in names}

        for channel in channels:
            name = channel["name"]
            value = sample[name]
            baseline = baseline_value(channel, mode_table[mode], sample, state, detector_cfg, dt_s)
            skip = in_grace and channel["baseline_type"] == "per_mode"
            status, rule = classify(value, channel, baseline, skip_relative=skip)
            deviation = None if baseline is None or _is_missing(value) else value - baseline
            out["t_s"].append(t_s)
            out["op_mode"].append(mode)
            out["channel"].append(name)
            out["value"].append(None if _is_missing(value) else value)
            out["baseline"].append(baseline)
            out["deviation"].append(deviation)
            out["status"].append(status)
            out["rule"].append(rule)
            out["in_grace"].append(in_grace)
    return pd.DataFrame(out)


def rollup(statuses: list[str]) -> str:
    """Worst status in the list (CRITICAL > WARNING > UNKNOWN > NORMAL). Empty -> NORMAL."""
    worst = "NORMAL"
    for status in statuses:
        if STATUS_ORDER[status] > STATUS_ORDER[worst]:
            worst = status
    return worst


def health_score(subsystem_statuses: dict[str, str], detector_cfg: dict) -> int | None:
    """0-100 score from detector.json health_score (placeholder rule: minimum of
    status_points over subsystems). None if every subsystem is UNKNOWN."""
    points = detector_cfg["health_score"]["status_points"]
    scores = [points[status] for status in subsystem_statuses.values() if status in points]
    return min(scores) if scores else None


def _round(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else round(float(value), 4)


def build_snapshot(evaluated: pd.DataFrame, robot_id: str, channels_cfg: dict, detector_cfg: dict,
                   start_time_utc: str, check: bool = True) -> dict:
    """health_snapshot contract for the LAST sample in `evaluated`, validated unless
    check=False (the per-batch analysis skips it for speed and validates before writing)."""
    last_t = int(evaluated["t_s"].max())
    latest = evaluated[evaluated["t_s"] == last_t]
    by_channel = {row["channel"]: row for row in latest.to_dict("records")}
    units = {channel["name"]: channel["units"] for channel in channels_cfg["channels"]}

    subsystems = []
    for subsystem in channels_cfg["hierarchy"]["subsystems"]:
        components = []
        for component_id in subsystem["components"]:
            entries = []
            for channel in channels_cfg["channels"]:
                if channel["component"] != component_id:
                    continue
                row = by_channel[channel["name"]]
                entries.append({
                    "channel": channel["name"], "units": units[channel["name"]],
                    "value": _round(row["value"]), "baseline": _round(row["baseline"]),
                    "deviation": _round(row["deviation"]), "status": row["status"],
                    "rule": row["rule"] if isinstance(row["rule"], str) else None,  # pandas may turn None into NaN
                })
            components.append({"component": component_id, "status": rollup([e["status"] for e in entries]),
                               "channels": entries})
        subsystems.append({"subsystem": subsystem["id"], "status": rollup([c["status"] for c in components]),
                           "components": components})

    start = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ")
    snapshot = {
        "schema_version": "1.0.0",
        "robot_id": robot_id,
        "robot_type": channels_cfg["robot_type"],
        "t_s": last_t,
        "timestamp": (start + timedelta(seconds=last_t)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "op_mode": latest["op_mode"].iloc[0],
        "status": rollup([s["status"] for s in subsystems]),
        "health_score": health_score({s["subsystem"]: s["status"] for s in subsystems}, detector_cfg),
        "subsystems": subsystems,
    }
    if check:
        validate(snapshot, "health_snapshot")
    return snapshot
