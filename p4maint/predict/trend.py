"""Trend fitting and time-to-failure extrapolation (Mission 3).

Responsibility: for a channel of one robot, fit the recent DEVIATION FROM BASELINE
(not the raw value, so a mode change is not mistaken for a trend), and if it is
heading toward the channel's CRITICAL limit, estimate when it will get there.

Settings: detector.json "trend" and "predictive_warning".
  - window: fit_window_s (30 min); need at least min_points samples
  - which samples: never the mode-change grace period (smoothing artefacts); wheel
    channels only while driving (evaluation.driving_modes); battery voltage only
    under load, scaled to the reference-mode load (see below)
  - model: linear (least squares). The bearing_wear fault accelerates (exponent 2),
    so a straight line OVERestimates time-to-failure; scoring measures by how much.
  - trust the fit only if r_squared >= min_r_squared AND |slope| >= min_slope_sigma
    standard errors
  - ttf = (critical_limit - current_deviation) / slope; ignored if the slope points
    away from the limit or ttf > max_horizon_s
  - interval at interval_confidence (80%) from the slope's standard error

Battery voltage: the sag from a degraded pack is I * delta_R, so it is bigger at high
load. Each sample's deviation is scaled by I_reference / I (I_reference = the
battery_current_a baseline in the reference mode), which turns it into "the sag this
pack would show at reference load" - the same terms the CRITICAL limit was calibrated
in. Samples below half the reference current are skipped.
"""

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from p4maint.configs import get_mode


def fit_linear_trend(t_s: np.ndarray, deviation: np.ndarray) -> dict | None:
    """Least-squares line through (t_s, deviation). NaNs are dropped first.

    Returns {"slope_per_s", "intercept_at_end", "r_squared", "n_points", "slope_stderr",
    "end_t_s"} or None if there are fewer than 3 points or no spread in time.
    """
    t_s = np.asarray(t_s, dtype=float)
    deviation = np.asarray(deviation, dtype=float)
    keep = ~np.isnan(t_s) & ~np.isnan(deviation)
    t_s, deviation = t_s[keep], deviation[keep]
    n = len(t_s)
    if n < 3:
        return None
    t_mean, y_mean = t_s.mean(), deviation.mean()
    sxx = float(((t_s - t_mean) ** 2).sum())
    if sxx == 0:
        return None
    slope = float(((t_s - t_mean) * (deviation - y_mean)).sum() / sxx)
    intercept = y_mean - slope * t_mean
    fitted = intercept + slope * t_s
    ss_res = float(((deviation - fitted) ** 2).sum())
    ss_tot = float(((deviation - y_mean) ** 2).sum())
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    stderr = math.sqrt(ss_res / (n - 2) / sxx)
    end_t_s = float(t_s.max())
    return {"slope_per_s": slope, "intercept_at_end": intercept + slope * end_t_s,
            "r_squared": max(0.0, r_squared), "n_points": n, "slope_stderr": stderr, "end_t_s": end_t_s}


def is_significant(trend: dict, detector_cfg: dict) -> bool:
    """True if the fit is good enough to extrapolate (enough points, R^2 and slope tests)."""
    settings = detector_cfg["trend"]
    if trend["n_points"] < settings["min_points"] or trend["r_squared"] < settings["min_r_squared"]:
        return False
    return abs(trend["slope_per_s"]) >= settings["min_slope_sigma"] * trend["slope_stderr"]


def time_to_threshold(trend: dict, limit_offset: float, detector_cfg: dict, side: str) -> dict | None:
    """Seconds from the end of the fit until the fitted deviation reaches limit_offset.

    side is "high" (a ceiling: crossed by rising past it) or "low" (a floor: crossed by
    falling past it). Returns {"ttf_s", "low_s", "high_s", "confidence_level"}, ttf 0 if
    already past the limit, or None when the trend is moving away from the limit or the
    crossing is beyond max_horizon_s.
    """
    settings = detector_cfg["trend"]
    slope, now = trend["slope_per_s"], trend["intercept_at_end"]
    gap = limit_offset - now
    already_past = now >= limit_offset if side == "high" else now <= limit_offset
    if already_past:
        return {"ttf_s": 0.0, "low_s": 0.0, "high_s": 0.0, "confidence_level": settings["interval_confidence"]}
    heading_there = slope > 0 if side == "high" else slope < 0
    if not heading_there:
        return None
    ttf = gap / slope
    if ttf > settings["max_horizon_s"]:
        return None
    z = NormalDist().inv_cdf(0.5 + settings["interval_confidence"] / 2)
    fast = abs(slope) + z * trend["slope_stderr"]
    slow = abs(slope) - z * trend["slope_stderr"]
    low = abs(gap) / fast
    high = abs(gap) / slow if slow > 0 else settings["max_horizon_s"]
    return {"ttf_s": ttf, "low_s": low, "high_s": min(high, settings["max_horizon_s"]),
            "confidence_level": settings["interval_confidence"]}


def _signal(evaluated_window: pd.DataFrame, channel_cfg: dict, modes_cfg: dict, detector_cfg: dict,
            now_t_s: int) -> tuple[np.ndarray, np.ndarray]:
    """(t_s, y) to fit for one channel over the fit window (see module docstring)."""
    window = evaluated_window[(evaluated_window["t_s"] > now_t_s - detector_cfg["trend"]["fit_window_s"])]
    rows = window[(window["channel"] == channel_cfg["name"]) & ~window["in_grace"]].sort_values("t_s")
    if channel_cfg["component"].startswith("wheel_"):
        rows = rows[rows["op_mode"].isin(detector_cfg["evaluation"]["driving_modes"])]
    if channel_cfg["limits"]["type"] == "absolute":
        return rows["t_s"].to_numpy(dtype=float), rows["value"].to_numpy(dtype=float)
    if channel_cfg["baseline_type"] == "battery_model":
        reference_mode = modes_cfg["reference_mode"]
        reference_current = get_mode(modes_cfg, reference_mode)["baselines"]["battery_current_a"]
        currents = window[window["channel"] == "battery_current_a"].set_index("t_s")["value"]
        current = currents.reindex(rows["t_s"]).to_numpy(dtype=float)
        loaded = current >= 0.5 * reference_current
        scaled = rows["deviation"].to_numpy(dtype=float) * reference_current / np.where(loaded, current, np.nan)
        return rows["t_s"].to_numpy(dtype=float)[loaded], scaled[loaded]
    return rows["t_s"].to_numpy(dtype=float), rows["deviation"].to_numpy(dtype=float)


def trend_for_channel(evaluated_window: pd.DataFrame, channel_cfg: dict, modes_cfg: dict,
                      detector_cfg: dict, now_t_s: int) -> dict | None:
    """Fit + significance + extrapolation for one channel over the fit window.

    Returns {"channel", "trend", "ttf", "limit_rule", "limit_offset", "now_t_s"} or None if
    there is no meaningful trend toward a CRITICAL limit. The high or low CRITICAL line is
    chosen by the slope's sign. Absolute-limit channels (battery_soc_pct) are fitted on the
    raw value instead of a deviation.
    """
    t_s, y = _signal(evaluated_window, channel_cfg, modes_cfg, detector_cfg, now_t_s)
    trend = fit_linear_trend(t_s, y)
    if trend is None or not is_significant(trend, detector_cfg):
        return None
    limits = channel_cfg["limits"]
    side = "high" if trend["slope_per_s"] > 0 else "low"
    offset = limits[f"critical_{side}"]
    if offset is None:
        return None
    kind = "ABSOLUTE" if limits["type"] == "absolute" else "RELATIVE"
    ttf = time_to_threshold(trend, offset, detector_cfg, side)
    if ttf is None:
        return None
    # The fit ends at the last usable sample, which may be before now (e.g. a parked wheel).
    elapsed = now_t_s - trend["end_t_s"]
    for key in ["ttf_s", "low_s", "high_s"]:
        ttf[key] = max(0.0, ttf[key] - elapsed)
    return {"channel": channel_cfg["name"], "trend": trend, "ttf": ttf,
            "limit_rule": f"{kind}_CRITICAL_{side.upper()}", "limit_offset": offset, "now_t_s": now_t_s}


def trends_for_robot(evaluated_window: pd.DataFrame, channels_cfg: dict, modes_cfg: dict,
                     detector_cfg: dict, now_t_s: int) -> list[dict]:
    """trend_for_channel() for every channel; those that found a trend, soonest failure first."""
    found = []
    for channel in channels_cfg["channels"]:
        estimate = trend_for_channel(evaluated_window, channel, modes_cfg, detector_cfg, now_t_s)
        if estimate is not None:
            found.append(estimate)
    return sorted(found, key=lambda e: e["ttf"]["ttf_s"])
