"""Score a finished run against its answer key. Headline metric: WARNING LEAD TIME.

Responsibility: after a run, read runs/<run_id>/answer_key/ground_truth.json (the
only module allowed to) and the event log, and write runs/<run_id>/score.json
(schemas/score.schema.json).

Definitions:
  warning lead time  = true failure_t_s - made_at_t_s of the FIRST predictive warning
                       (predict.prediction.is_predictive_warning) on that robot whose
                       fault_mode matches the injected fault. Mission 3 target: >= 900 s.
  detection delay    = t_s of the first anomaly on the faulty robot - inject_t_s
  diagnosis correct  = fault_mode of the first predictive warning on that robot
                       == injected fault_type
  false alarms       = anomalies, predictive warnings and work orders on robots with no
                       injected fault (healthy_baseline must score 0 on all three)
  missed             = injected fault with no correct predictive warning before failure_t_s
"""

import json
from pathlib import Path

from p4maint import paths
from p4maint.generator.ground_truth import answer_key_path
from p4maint.predict.prediction import is_predictive_warning
from schemas.validate import validate


def load_answer_key(run_folder: Path) -> dict:
    """Read and validate the answer key."""
    truth = json.loads(answer_key_path(run_folder).read_text())
    validate(truth, "ground_truth")
    return truth


def load_events(run_folder: Path) -> list[dict]:
    path = paths.events_path(run_folder)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def first_predictive_warning(events: list[dict], robot_id: str, detector_cfg: dict,
                             fault_mode: str | None = None) -> dict | None:
    """The earliest PREDICTION_ISSUED payload for robot_id that counts as a predictive
    warning (optionally only ones naming fault_mode)."""
    for event in events:
        if event["type"] != "PREDICTION_ISSUED" or event["robot_id"] != robot_id:
            continue
        prediction = event["payload"]
        if not is_predictive_warning(prediction, detector_cfg):
            continue
        if fault_mode is None or prediction["fault_mode"] == fault_mode:
            return prediction
    return None


def warning_lead_time_s(fault_truth: dict, warning: dict | None) -> float | None:
    """failure_t_s - warning made_at_t_s, or None if there was no warning before failure."""
    if warning is None or warning["made_at_t_s"] >= fault_truth["failure_t_s"]:
        return None
    return float(fault_truth["failure_t_s"] - warning["made_at_t_s"])


def score_run(run_folder: Path, detector_cfg: dict) -> dict:
    """Every metric above, per injected fault and for the run; validated and written to score.json."""
    truth = load_answer_key(run_folder)
    events = load_events(run_folder)
    target = detector_cfg["predictive_warning"]["target_lead_time_s"]
    faulty_robots = {fault["robot_id"] for fault in truth["faults"]}

    fault_scores = []
    for fault in truth["faults"]:
        robot_id = fault["robot_id"]
        anomalies = [e for e in events if e["type"] == "ANOMALY_RAISED" and e["robot_id"] == robot_id
                     and e["payload"]["t_s"] >= fault["inject_t_s"]]
        first_anomaly = min((e["payload"]["t_s"] for e in anomalies), default=None)
        first_any = first_predictive_warning(events, robot_id, detector_cfg)
        first_right = first_predictive_warning(events, robot_id, detector_cfg, fault["fault_type"])
        lead = warning_lead_time_s(fault, first_right)
        predicted = None if lead is None else first_right["predicted_failure_t_s"]
        fault_scores.append({
            "fault_id": fault["fault_id"], "robot_id": robot_id, "fault_type": fault["fault_type"],
            "inject_t_s": fault["inject_t_s"], "failure_t_s": fault["failure_t_s"],
            "first_anomaly_t_s": first_anomaly,
            "detection_delay_s": None if first_anomaly is None else first_anomaly - fault["inject_t_s"],
            "first_warning_t_s": None if first_any is None else first_any["made_at_t_s"],
            "first_warning_fault_mode": None if first_any is None else first_any["fault_mode"],
            "diagnosis_correct": None if first_any is None else first_any["fault_mode"] == fault["fault_type"],
            "warning_lead_time_s": lead,
            "predicted_failure_t_s": predicted,
            "failure_time_error_s": None if predicted is None else round(predicted - fault["failure_t_s"], 1),
            "missed": lead is None,
            "meets_target": lead is not None and lead >= target,
        })

    healthy_events = [e for e in events if e["robot_id"] is not None and e["robot_id"] not in faulty_robots]
    false_alarms = {
        "anomalies": sum(1 for e in healthy_events if e["type"] == "ANOMALY_RAISED"),
        "predictive_warnings": sum(1 for e in healthy_events if e["type"] == "PREDICTION_ISSUED"
                                   and is_predictive_warning(e["payload"], detector_cfg)),
        "work_orders": sum(1 for e in healthy_events if e["type"] == "WORK_ORDER_CREATED"),
    }
    met = sum(1 for f in fault_scores if f["meets_target"])
    summary = (f"{met} of {len(fault_scores)} faults warned at least {target:.0f} s early; "
               f"false alarms: {false_alarms['anomalies']} anomalies, {false_alarms['predictive_warnings']} "
               f"predictive warnings, {false_alarms['work_orders']} work orders")
    score = {"schema_version": "1.0.0", "run_id": truth["run_id"], "scenario_id": truth["scenario_id"],
             "target_lead_time_s": target, "faults": fault_scores, "false_alarms": false_alarms, "summary": summary}
    validate(score, "score")
    paths.score_path(run_folder).write_text(json.dumps(score, indent=2) + "\n")
    return score
