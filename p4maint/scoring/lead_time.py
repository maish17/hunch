"""Score a finished run against its answer key. Headline metric: WARNING LEAD TIME.

Responsibility: after a run, read runs/<run_id>/answer_key/ground_truth.json (the
only module allowed to) and the event log, and write runs/<run_id>/score.json.

Definitions:
  warning lead time  = true failure_t_s - made_at_t_s of the FIRST predictive warning
                       (predict.prediction.is_predictive_warning) for that robot whose
                       fault_mode matches. Mission 3 target: >= 900 s (15 min).
  detection delay    = detected_t_s of the first anomaly on the faulty robot - inject_t_s
  diagnosis correct  = fault_mode of that first warning == injected fault_type
  false positives    = work orders on robots with no injected fault (healthy_baseline
                       must score 0)
  missed             = injected fault with no predictive warning before failure_t_s

STATUS: stubs.
"""

from pathlib import Path


def load_answer_key(run_folder: Path) -> dict:
    """Read and validate the answer key (p4maint.generator.ground_truth.answer_key_path)."""
    raise NotImplementedError("load_answer_key")


def first_predictive_warning(events: list[dict], robot_id: str, detector_cfg: dict) -> dict | None:
    """The earliest PREDICTION_ISSUED payload for robot_id that counts as a predictive warning."""
    raise NotImplementedError("first_predictive_warning")


def warning_lead_time_s(fault_truth: dict, warning: dict | None) -> float | None:
    """failure_t_s - warning made_at_t_s, or None if there was no warning before failure."""
    raise NotImplementedError("warning_lead_time_s")


def score_run(run_folder: Path, detector_cfg: dict) -> dict:
    """Every metric above, per injected fault and for the run; written to score.json."""
    raise NotImplementedError("score_run")
