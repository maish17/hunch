"""Assemble the prediction contract (Missions 3 + 4 together).

Responsibility: combine a diagnosis (which fault, how sure) with a trend estimate
(when) and the evidence window into one prediction (schemas/prediction.schema.json),
and decide whether it is urgent enough to be a predictive warning.

STATUS: stubs.
"""


def new_prediction_id(number: int) -> str:
    """PR-000001 style id. number starts at 1 for each run."""
    raise NotImplementedError("new_prediction_id")


def build_prediction(prediction_id: str, robot_id: str, diagnosis: dict, trend_estimate: dict | None,
                     anomaly_ids: list[str], now_t_s: int, start_time_utc: str, evidence_channels: list[str],
                     detector_cfg: dict) -> dict:
    """Build and validate a prediction dict.

    trend_estimate is for diagnosis["target_channel"] (or None: then predicted_ttf_s,
    the interval, predicted_failure_t_s and trend are null). The evidence window runs
    from now - detector.json trend.fit_window_s to now, source "telemetry.parquet".
    Severity comes from diagnose.diagnosis.severity_for().
    """
    raise NotImplementedError("build_prediction")


def is_predictive_warning(prediction: dict, detector_cfg: dict) -> bool:
    """True when predicted_ttf_s < predictive_warning.warn_if_ttf_below_s and
    confidence >= predictive_warning.min_confidence. This is the moment scoring
    measures lead time from."""
    raise NotImplementedError("is_predictive_warning")
