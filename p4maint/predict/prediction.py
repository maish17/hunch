"""Assemble the prediction contract (Missions 3 + 4 together).

Responsibility: combine a diagnosis (which fault, how sure) with a trend estimate
(when) and the evidence window into one prediction (schemas/prediction.schema.json),
decide whether it is urgent enough to be a predictive warning, and whether it has
changed enough to be announced again.
"""

from datetime import datetime, timedelta

from p4maint.configs import get_channel
from p4maint.diagnose.diagnosis import severity_for
from schemas.validate import validate


def new_prediction_id(number: int) -> str:
    """PR-000001 style id. number starts at 1 for each run."""
    return f"PR-{number:06d}"


def evidence_channels_for(diagnosis: dict, channels_cfg: dict) -> list[str]:
    """Channels a prediction's evidence window covers: the target channel first, then every
    channel on the same wheel (current, speed, temperature) or the same component."""
    target = diagnosis["target_channel"]
    component = diagnosis["component"]
    names = [target]
    for channel in channels_cfg["channels"]:
        same_wheel = component.startswith("wheel_") and channel["component"].split("_")[:2] == component.split("_")[:2]
        if (same_wheel or channel["component"] == component) and channel["name"] not in names:
            names.append(channel["name"])
    return names


def build_prediction(prediction_id: str, robot_id: str, diagnosis: dict, trend_estimate: dict | None,
                     target_baseline: float | None, anomaly_ids: list[str], now_t_s: int, start_time_utc: str,
                     channels_cfg: dict, faults_cfg: dict, detector_cfg: dict) -> dict:
    """Build and validate a prediction dict.

    trend_estimate is predict.trend.trend_for_channel() for diagnosis["target_channel"], or
    None (then predicted_ttf_s, the interval, predicted_failure_t_s and trend are null).
    target_baseline is that channel's current baseline, used to state the threshold as an
    absolute value. The evidence window runs from now - trend.fit_window_s to now.
    """
    channel = get_channel(channels_cfg, diagnosis["target_channel"])
    limits = channel["limits"]
    kind = "ABSOLUTE" if limits["type"] == "absolute" else "RELATIVE"
    if trend_estimate is not None:
        rule, limit = trend_estimate["limit_rule"], trend_estimate["limit_offset"]
    elif limits["critical_high"] is not None:
        rule, limit = f"{kind}_CRITICAL_HIGH", limits["critical_high"]
    else:
        rule, limit = f"{kind}_CRITICAL_LOW", limits["critical_low"]
    if kind == "ABSOLUTE" or target_baseline is None:
        value_at_threshold = limit
    else:
        value_at_threshold = target_baseline + limit

    if trend_estimate is not None:
        ttf = trend_estimate["ttf"]
        fit = trend_estimate["trend"]
        ttf_s = round(ttf["ttf_s"], 1)
        interval = {"low": round(ttf["low_s"], 1), "high": round(ttf["high_s"], 1), "confidence_level": ttf["confidence_level"]}
        failure_t_s = round(now_t_s + ttf["ttf_s"], 1)
        trend = {"model": "linear", "slope_per_s": fit["slope_per_s"], "intercept": round(fit["intercept_at_end"], 4),
                 "r_squared": round(fit["r_squared"], 4), "n_points": fit["n_points"], "units": channel["units"]}
    else:
        ttf_s, interval, failure_t_s, trend = None, None, None, None

    start = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ")
    prediction = {
        "schema_version": "1.0.0",
        "prediction_id": prediction_id,
        "robot_id": robot_id,
        "made_at_t_s": now_t_s,
        "made_at": (start + timedelta(seconds=now_t_s)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fault_mode": diagnosis["fault_mode"],
        "confidence": diagnosis["confidence"],
        "component": diagnosis["component"],
        "subsystem": diagnosis["subsystem"],
        "severity": severity_for(diagnosis["fault_mode"], ttf_s, diagnosis["any_channel_critical"], faults_cfg, detector_cfg),
        "candidates": diagnosis["candidates"],
        "target_channel": diagnosis["target_channel"],
        "failure_threshold": {"rule": rule, "limit": limit, "value_at_threshold": round(value_at_threshold, 4)},
        "predicted_ttf_s": ttf_s,
        "predicted_ttf_interval_s": interval,
        "predicted_failure_t_s": failure_t_s,
        "trend": trend,
        "signature_observed": diagnosis["signature_observed"],
        "residuals": diagnosis["residuals"],
        "anomaly_ids": anomaly_ids,
        "evidence_window": {"robot_id": robot_id,
                            "start_t_s": max(0, now_t_s - detector_cfg["trend"]["fit_window_s"]),
                            "end_t_s": now_t_s,
                            "channels": evidence_channels_for(diagnosis, channels_cfg),
                            "source": "telemetry.parquet"},
    }
    validate(prediction, "prediction")
    return prediction


def is_predictive_warning(prediction: dict, detector_cfg: dict) -> bool:
    """True when predicted_ttf_s < predictive_warning.warn_if_ttf_below_s and
    confidence >= predictive_warning.min_confidence for a named fault. This is the
    moment scoring measures lead time from."""
    settings = detector_cfg["predictive_warning"]
    ttf = prediction["predicted_ttf_s"]
    return (ttf is not None and ttf < settings["warn_if_ttf_below_s"]
            and prediction["fault_mode"] != "unknown"
            and prediction["confidence"] >= settings["min_confidence"])


def should_publish(previous: dict | None, new: dict, detector_cfg: dict) -> bool:
    """Announce a new prediction (log PREDICTION_ISSUED) only when it says something new:
    the first one for the robot, a different fault, severity or warning state, a time to
    failure appearing, or the predicted failure time moving by more than
    republish_change_fraction of the time left (and at least republish_min_change_s)."""
    if previous is None:
        return True
    for key in ["fault_mode", "severity", "target_channel"]:
        if previous[key] != new[key]:
            return True
    if is_predictive_warning(previous, detector_cfg) != is_predictive_warning(new, detector_cfg):
        return True
    old_fail, new_fail = previous["predicted_failure_t_s"], new["predicted_failure_t_s"]
    if new_fail is None:
        return False          # trend lost (e.g. after a stop): the last prediction stands
    if old_fail is None:
        return True           # a time to failure has appeared
    settings = detector_cfg["predictive_warning"]
    needed = max(settings["republish_change_fraction"] * new["predicted_ttf_s"], settings["republish_min_change_s"])
    return abs(new_fail - old_fail) > needed
