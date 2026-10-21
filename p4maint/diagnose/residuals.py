"""Derived signals that separate faults which look alike on raw channels.

Responsibility: compute the two residuals defined in config/faults.json
"derived_signals", using ONLY the detector's own models in detector.json:

  thermal_residual  measured drive temperature - temperature predicted from measured
                    current and speed. The detector's thermal model is run over the
                    window: P = I^2 * R_arm + tau_b0 * omega, then a first-order lag
                    toward sink + P * R_th with time constant tau_s. Positive = heat the
                    current does not explain. THE key signal: bearing_wear > 0, wheel_drag ~ 0.
  voltage_residual  measured battery voltage - (V_oc(SOC) - I * R_nominal).
                    Negative = extra sag. battery_degradation < 0, worse at high current.

Both are averaged over the latest detector.json diagnosis.recent_samples relevant
samples (driving samples for a wheel, high-load samples for the battery).
"""

import numpy as np
import pandas as pd


def _driving(df: pd.DataFrame, detector_cfg: dict) -> pd.Series:
    return df["op_mode"].isin(detector_cfg["evaluation"]["driving_modes"])


def predicted_drive_temp_c(window_df: pd.DataFrame, wheel: str, detector_cfg: dict) -> pd.Series:
    """Temperature the detector's thermal model expects for one wheel ("fl", "fr", "rl", "rr"),
    one value per row of window_df (raw telemetry, sorted by t_s). The model starts at the
    first measured temperature, so the window should be long compared with tau_s."""
    model = detector_cfg["thermal_model"]
    rows = window_df.sort_values("t_s")
    current = rows[f"wheel_{wheel}_current_a"].ffill().fillna(0.0).to_numpy(dtype=float)
    speed = rows[f"wheel_{wheel}_speed_rads"].ffill().fillna(0.0).to_numpy(dtype=float)
    measured = rows[f"wheel_{wheel}_temp_c"].to_numpy(dtype=float)
    t_s = rows["t_s"].to_numpy(dtype=float)

    predicted = np.empty(len(rows))
    temp = measured[0] if len(rows) and not np.isnan(measured[0]) else model["sink_temp_c"]
    for k in range(len(rows)):
        predicted[k] = temp
        heat = current[k] ** 2 * model["r_arm_ohm"] + model["bearing_friction_nm"] * speed[k]
        steady = model["sink_temp_c"] + heat * model["r_th_k_per_w"]
        dt_s = t_s[k + 1] - t_s[k] if k + 1 < len(rows) else 0.0
        temp += dt_s / model["tau_s"] * (steady - temp)
    return pd.Series(predicted, index=rows.index)


def thermal_residual_c(window_df: pd.DataFrame, wheel: str, detector_cfg: dict) -> float | None:
    """Mean of (measured - predicted) temperature over the latest recent_samples driving
    samples. None if the wheel did not drive in the window."""
    if window_df.empty:
        return None
    rows = window_df.sort_values("t_s")
    residual = rows[f"wheel_{wheel}_temp_c"] - predicted_drive_temp_c(rows, wheel, detector_cfg)
    driving = residual[_driving(rows, detector_cfg)].dropna()
    if driving.empty:
        return None
    return float(driving.tail(detector_cfg["diagnosis"]["recent_samples"]).mean())


def voltage_residual_v(window_df: pd.DataFrame, detector_cfg: dict) -> float | None:
    """Mean voltage residual over the high-load samples (battery current at or above the
    median) among the latest recent_samples rows. None if there is no load."""
    if window_df.empty:
        return None
    model = detector_cfg["battery_model"]
    table = np.array(model["ocv_table_soc_pct_to_v"], dtype=float)
    rows = window_df.sort_values("t_s").tail(detector_cfg["diagnosis"]["recent_samples"])
    current = rows["battery_current_a"].to_numpy(dtype=float)
    expected = np.interp(rows["battery_soc_pct"].to_numpy(dtype=float), table[:, 0], table[:, 1]) - current * model["r_int_nominal_ohm"]
    residual = rows["battery_voltage_v"].to_numpy(dtype=float) - expected
    loaded = (current > 0) & (current >= np.nanmedian(current))
    values = residual[loaded & ~np.isnan(residual)]
    if len(values) == 0:
        return None
    return float(values.mean())


def channel_shift(evaluated_window: pd.DataFrame, channel: str, detector_cfg: dict,
                  driving_only: bool = False) -> float | None:
    """Median deviation from baseline of one channel over its latest recent_samples samples
    (only driving samples if driving_only). The median ignores the brief swings around
    mode changes. None if there are no samples."""
    rows = evaluated_window[(evaluated_window["channel"] == channel) & ~evaluated_window["in_grace"]]
    if driving_only:
        rows = rows[_driving(rows, detector_cfg)]
    deviation = rows.sort_values("t_s")["deviation"].dropna().tail(detector_cfg["diagnosis"]["recent_samples"])
    if deviation.empty:
        return None
    return float(deviation.median())
