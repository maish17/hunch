"""Derived signals that separate faults which look alike on raw channels.

Responsibility: compute the two residuals defined in config/faults.json
"derived_signals", using ONLY the detector's own models in detector.json:

  thermal_residual  measured drive temperature - temperature predicted from measured
                    current and speed. Run the detector's thermal model over the window:
                    P = I^2 * R_arm + tau_b0 * omega, then a first-order lag toward
                    sink + P * R_th with time constant tau_s. Positive = heat the current
                    does not explain. THE key signal: bearing_wear > 0, wheel_drag ~ 0.
  voltage_residual  measured battery voltage - (V_oc(SOC) - I * R_nominal).
                    Negative = extra sag. battery_degradation < 0, worse at high current.

STATUS: stubs.
"""

import pandas as pd


def predicted_drive_temp_c(window_df: pd.DataFrame, wheel: str, detector_cfg: dict) -> pd.Series:
    """Temperature the detector's thermal model expects for one wheel ("fl", "fr", "rl", "rr"),
    one value per row. Start the lag at the first measured temperature."""
    raise NotImplementedError("predicted_drive_temp_c")


def thermal_residual_c(window_df: pd.DataFrame, wheel: str, detector_cfg: dict) -> float | None:
    """Mean of (measured - predicted) temperature over the last 5 min of the window
    while the wheel is moving. None if the wheel did not move."""
    raise NotImplementedError("thermal_residual_c")


def voltage_residual_v(window_df: pd.DataFrame, detector_cfg: dict) -> float | None:
    """Mean voltage residual over the window's high-load samples (battery_current_a above
    its median). None if there is no load in the window."""
    raise NotImplementedError("voltage_residual_v")


def channel_shift(evaluated_window: pd.DataFrame, channel: str) -> float | None:
    """Mean deviation from baseline of one channel over the last 5 min of the window."""
    raise NotImplementedError("channel_shift")
