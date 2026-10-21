"""Diagnosis: which of the four faults, on which component, how sure (Mission 4).

Responsibility: turn multi-channel evidence into a ranked list of the four fault
types from config/faults.json and pick the most likely one, its component and a
severity. Rule-based - no machine learning (team decision).

Method (all thresholds from detector.json "diagnosis"):
  1. Localise: find the component whose channels have drifted furthest toward a
     WARNING limit (median deviation of recent samples / WARNING offset). Nothing is
     diagnosed until some component reaches localise_min_fraction.
  2. Observe: turn each signature element into UP / DOWN / NORMAL /
     EXPLAINED_BY_CURRENT using channel_shift() and the residuals:
        wheel_current     UP if shift >= current_rise_a, DOWN if <= -current_rise_a
        wheel_speed       DOWN if shift <= speed_drop_rads, UP if >= -speed_drop_rads
        thermal_residual  UP if >= thermal_residual_excess_c
        wheel_temp        UP if the thermal residual is UP; EXPLAINED_BY_CURRENT if the
                          temperature rose by temp_rise_c or more without excess heat
        voltage_residual  DOWN if <= voltage_residual_excess_v
     Evidence only counts as NORMAL when it is within normal_band_fraction of its
     threshold. In between it is UNCLEAR, which matches no fault, so a half-formed
     signature gives "unknown" rather than a confident wrong answer.
  3. Score: for each fault, the fraction of its signature elements that match.
  4. Pick the best (choose_fault). Report "unknown" if it is below min_confidence, tied
     with the runner-up, or missing any of its OWN distinctive (non-NORMAL) evidence.
     The last rule stops a fault winning by elimination: a flat battery raises a
     low-charge alert with every other element NORMAL, which would otherwise match 4 of
     battery_degradation's 5 elements even though no extra sag is seen.
  Central case: bearing_wear and wheel_drag differ ONLY in the temperature evidence.
"""

import pandas as pd

from p4maint.configs import get_fault
from p4maint.diagnose.residuals import thermal_residual_c, voltage_residual_v


def _is_wheel(channel_cfg: dict) -> bool:
    return channel_cfg["component"].startswith("wheel_")


def _wheel_of(component: str) -> str:
    """wheel_fl_drive -> fl."""
    return component.split("_")[1]


def recent_shifts(evaluated_window: pd.DataFrame, channels_cfg: dict, detector_cfg: dict) -> dict[str, float | None]:
    """Median recent deviation of every channel (same rule as residuals.channel_shift:
    wheel channels only while driving), computed with one pass over the window."""
    driving_modes = detector_cfg["evaluation"]["driving_modes"]
    recent = detector_cfg["diagnosis"]["recent_samples"]
    wheel_channels = {c["name"] for c in channels_cfg["channels"] if _is_wheel(c)}
    shifts = {c["name"]: None for c in channels_cfg["channels"]}
    # The rolling window is already in time order, so no sort is needed here.
    settled = evaluated_window[~evaluated_window["in_grace"]]
    for name, rows in settled.groupby("channel", sort=False):
        if name in wheel_channels:
            rows = rows[rows["op_mode"].isin(driving_modes)]
        deviation = rows["deviation"].dropna().tail(recent)
        if not deviation.empty:
            shifts[name] = float(deviation.median())
    return shifts


def component_scores(evaluated_window: pd.DataFrame, channels_cfg: dict, detector_cfg: dict,
                     shifts: dict | None = None) -> dict[str, tuple[float, str]]:
    """{component: (fraction, channel)}: how far the component's worst channel has drifted
    toward its WARNING limit, as a fraction of the WARNING offset (1.0 = at the limit)."""
    if shifts is None:
        shifts = recent_shifts(evaluated_window, channels_cfg, detector_cfg)
    scores = {}
    for channel in channels_cfg["channels"]:
        limits = channel["limits"]
        if limits["type"] != "relative":
            continue
        shift = shifts.get(channel["name"])
        if shift is None:
            continue
        offset = limits["warning_high"] if shift > 0 else limits["warning_low"]
        if not offset:
            continue
        fraction = shift / offset
        best = scores.get(channel["component"])
        if best is None or fraction > best[0]:
            scores[channel["component"]] = (fraction, channel["name"])
    return scores


def localise(evaluated_window: pd.DataFrame, channels_cfg: dict, detector_cfg: dict,
             scores: dict | None = None) -> str | None:
    """Component id whose channels are furthest toward a WARNING limit, e.g. "wheel_fl_thermal"
    or "battery_pack". None if nothing has reached localise_min_fraction."""
    if scores is None:
        scores = component_scores(evaluated_window, channels_cfg, detector_cfg)
    if not scores:
        return None
    component = max(scores, key=lambda c: scores[c][0])
    if scores[component][0] < detector_cfg["diagnosis"]["localise_min_fraction"]:
        return None
    return component


def observe_signature(window_df: pd.DataFrame, shifts: dict[str, float | None], wheel: str,
                      detector_cfg: dict) -> tuple[dict[str, str], dict[str, float | None]]:
    """(signature_observed, residuals) using the given wheel for the wheel elements.

    shifts is recent_shifts() of the evaluated window; window_df is raw telemetry for the
    residuals. signature_observed uses the keys in config/faults.json "signature";
    residuals is {"thermal_residual_c": ..., "voltage_residual_v": ...}.
    """
    diag = detector_cfg["diagnosis"]
    current = shifts.get(f"wheel_{wheel}_current_a")
    speed = shifts.get(f"wheel_{wheel}_speed_rads")
    temp = shifts.get(f"wheel_{wheel}_temp_c")
    thermal = thermal_residual_c(window_df, wheel, detector_cfg)
    voltage = voltage_residual_v(window_df, detector_cfg)

    band = diag["normal_band_fraction"]

    def direction(value, up_at, down_at):
        """UP / DOWN past the thresholds, NORMAL well inside them, UNCLEAR in between."""
        if value is None:
            return "NORMAL"
        if value >= up_at:
            return "UP"
        if value <= down_at:
            return "DOWN"
        if down_at * band < value < up_at * band:
            return "NORMAL"
        return "UNCLEAR"

    heat = direction(thermal, diag["thermal_residual_excess_c"], -float("inf"))
    if heat == "UP":
        wheel_temp = "UP"
    elif heat == "UNCLEAR":
        wheel_temp = "UNCLEAR"
    elif temp is not None and temp >= diag["temp_rise_c"]:
        wheel_temp = "EXPLAINED_BY_CURRENT"
    else:
        wheel_temp = "NORMAL"
    sag = direction(voltage, float("inf"), diag["voltage_residual_excess_v"])
    signature = {
        "wheel_current": direction(current, diag["current_rise_a"], -diag["current_rise_a"]),
        "wheel_speed": direction(speed, -diag["speed_drop_rads"], diag["speed_drop_rads"]),
        "wheel_temp": wheel_temp,
        "thermal_residual": heat,
        "voltage_residual": sag,
    }
    residuals = {"thermal_residual_c": None if thermal is None else round(thermal, 3),
                 "voltage_residual_v": None if voltage is None else round(voltage, 3)}
    return signature, residuals


def score_candidates(signature_observed: dict[str, str], faults_cfg: dict) -> list[dict]:
    """[{"fault_mode", "score"}] for all four faults, best first. score in [0, 1] is the
    fraction of the fault's signature elements that match what was observed."""
    candidates = []
    for fault in faults_cfg["faults"]:
        expected = fault["signature"]
        matches = sum(1 for key, value in expected.items() if signature_observed.get(key) == value)
        candidates.append({"fault_mode": fault["id"], "score": round(matches / len(expected), 3)})
    return sorted(candidates, key=lambda c: -c["score"])


def choose_fault(candidates: list[dict], signature_observed: dict[str, str], faults_cfg: dict,
                 detector_cfg: dict) -> str:
    """The fault to report, or "unknown" (rules in the module docstring, step 4)."""
    best, runner_up = candidates[0], candidates[1]
    if best["score"] < detector_cfg["diagnosis"]["min_confidence"] or best["score"] <= runner_up["score"]:
        return "unknown"
    expected = get_fault(faults_cfg, best["fault_mode"])["signature"]
    for key, value in expected.items():
        if value != "NORMAL" and signature_observed.get(key) != value:
            return "unknown"
    return best["fault_mode"]


def severity_for(fault_mode: str, ttf_s: float | None, any_channel_critical: bool,
                 faults_cfg: dict, detector_cfg: dict) -> str:
    """WARNING or CRITICAL, using detector.json severity_rules (CRITICAL if ttf is under
    critical_if_ttf_below_s or a channel is already CRITICAL, else the fault's
    consequence_severity; "unknown" faults default to WARNING)."""
    rules = detector_cfg["severity_rules"]
    if rules["critical_if_any_channel_critical"] and any_channel_critical:
        return "CRITICAL"
    if ttf_s is not None and ttf_s < rules["critical_if_ttf_below_s"]:
        return "CRITICAL"
    if fault_mode == "unknown":
        return "WARNING"
    return get_fault(faults_cfg, fault_mode)["consequence_severity"]


def _subsystem_of(component: str, channels_cfg: dict) -> str:
    for item in channels_cfg["hierarchy"]["components"]:
        if item["id"] == component:
            return item["subsystem"]
    raise KeyError(component)


def diagnose(robot_id: str, window_df: pd.DataFrame, evaluated_window: pd.DataFrame,
             active_anomalies: list[dict], channels_cfg: dict, faults_cfg: dict,
             detector_cfg: dict) -> dict | None:
    """Full diagnosis for one robot, or None if nothing is wrong.

    Returns {"fault_mode", "confidence", "component", "subsystem", "candidates",
    "signature_observed", "residuals", "target_channel", "any_channel_critical"} where
    target_channel is the fault's primary channel on that component (e.g. wheel_fl_temp_c).
    """
    if evaluated_window.empty:
        return None
    shifts = recent_shifts(evaluated_window, channels_cfg, detector_cfg)
    scores = component_scores(evaluated_window, channels_cfg, detector_cfg, shifts)
    located = localise(evaluated_window, channels_cfg, detector_cfg, scores)
    if located is None and not active_anomalies:
        return None
    if located is None:
        located = active_anomalies[0]["component"]

    wheel_scores = {c: s for c, s in scores.items() if c.startswith("wheel_")}
    if located.startswith("wheel_"):
        wheel = _wheel_of(located)
    elif wheel_scores:
        wheel = _wheel_of(max(wheel_scores, key=lambda c: wheel_scores[c][0]))
    else:
        wheel = _wheel_of(next(c["id"] for c in channels_cfg["hierarchy"]["components"] if c["id"].startswith("wheel_")))

    signature, residuals = observe_signature(window_df, shifts, wheel, detector_cfg)
    candidates = score_candidates(signature, faults_cfg)
    best = candidates[0]
    fault_mode = choose_fault(candidates, signature, faults_cfg, detector_cfg)

    if fault_mode != "unknown":
        fault = get_fault(faults_cfg, fault_mode)
        component = fault["component_pattern"].replace("{wheel}", wheel)
        target_channel = fault["primary_channel_pattern"].replace("{wheel}", wheel)
        subsystem = fault["subsystem"]
    else:
        component = located
        target_channel = scores[located][1] if located in scores else active_anomalies[0]["channel"]
        subsystem = _subsystem_of(located, channels_cfg)

    latest = evaluated_window[evaluated_window["t_s"] == evaluated_window["t_s"].max()]
    return {
        "fault_mode": fault_mode,
        "confidence": best["score"],
        "component": component,
        "subsystem": subsystem,
        "candidates": candidates,
        "signature_observed": signature,
        "residuals": residuals,
        "target_channel": target_channel,
        "any_channel_critical": bool((latest["status"] == "CRITICAL").any()),
    }
