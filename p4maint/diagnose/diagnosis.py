"""Diagnosis: which of the four faults, on which component, how sure (Mission 4).

Responsibility: turn multi-channel evidence into a ranked list of the four fault
types from config/faults.json and pick the most likely one, its component and a
severity. Rule-based - no machine learning (team decision).

Method (all thresholds from detector.json "diagnosis"):
  1. Localise: find the component whose channels deviate most (e.g. which wheel).
  2. Observe: turn each signature element into UP / DOWN / NORMAL /
     EXPLAINED_BY_CURRENT using channel_shift() and the residuals:
        wheel_current     UP if shift > current_rise_a
        wheel_speed       DOWN if shift < speed_drop_rads
        wheel_temp        UP if thermal residual > thermal_residual_excess_c,
                          EXPLAINED_BY_CURRENT if it rose but the residual did not
        thermal_residual  UP if > thermal_residual_excess_c
        voltage_residual  DOWN if < voltage_residual_excess_v
  3. Score: for each fault, fraction of its signature elements that match.
  4. Pick the best; below min_confidence report fault_mode "unknown".
  Central case: bearing_wear and wheel_drag differ ONLY in the temperature evidence.

STATUS: stubs. This is Mission 4 logic for the team to write.
"""

import pandas as pd


def localise(evaluated_window: pd.DataFrame, channels_cfg: dict) -> str | None:
    """Component id whose channels are furthest from baseline (in units of their WARNING
    offsets), e.g. "wheel_fl_drive" or "battery_pack". None if everything is near baseline."""
    raise NotImplementedError("localise")


def observe_signature(window_df: pd.DataFrame, evaluated_window: pd.DataFrame, component: str,
                      detector_cfg: dict) -> tuple[dict[str, str], dict[str, float | None]]:
    """(signature_observed, residuals) for the suspect component.

    signature_observed uses the keys in config/faults.json "signature"; residuals is
    {"thermal_residual_c": ..., "voltage_residual_v": ...}.
    """
    raise NotImplementedError("observe_signature")


def score_candidates(signature_observed: dict[str, str], faults_cfg: dict) -> list[dict]:
    """[{"fault_mode", "score"}] for all four faults, best first. score in [0, 1]."""
    raise NotImplementedError("score_candidates")


def severity_for(fault_mode: str, ttf_s: float | None, any_channel_critical: bool,
                 faults_cfg: dict, detector_cfg: dict) -> str:
    """WARNING or CRITICAL, using detector.json severity_rules (CRITICAL if ttf is under
    critical_if_ttf_below_s or a channel is already CRITICAL, else the fault's
    consequence_severity; "unknown" faults default to WARNING)."""
    raise NotImplementedError("severity_for")


def diagnose(robot_id: str, window_df: pd.DataFrame, evaluated_window: pd.DataFrame,
             active_anomalies: list[dict], channels_cfg: dict, faults_cfg: dict,
             detector_cfg: dict) -> dict | None:
    """Full diagnosis for one robot, or None if nothing is wrong.

    Returns {"fault_mode", "confidence", "component", "subsystem", "candidates",
    "signature_observed", "residuals", "target_channel"} where target_channel is the
    fault's primary channel on that component (e.g. wheel_fl_temp_c).
    """
    raise NotImplementedError("diagnose")
