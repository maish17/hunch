"""Scoring against the answer key (p4maint/scoring/lead_time.py)."""

import json
import tempfile
import unittest
from pathlib import Path

from p4maint import configs
from p4maint.generator.ground_truth import build_ground_truth, write_ground_truth
from p4maint.generator.scenario import load_scenario
from p4maint.paths import SCENARIOS_DIR
from p4maint.scoring.lead_time import first_predictive_warning, score_run, warning_lead_time_s
from schemas.validate import validate

DETECTOR = configs.load_detector_params()


def prediction_event(robot_id: str, made_at: int, fault_mode: str, ttf: float | None, confidence: float = 1.0) -> dict:
    payload = {"made_at_t_s": made_at, "fault_mode": fault_mode, "confidence": confidence, "predicted_ttf_s": ttf,
               "predicted_failure_t_s": None if ttf is None else made_at + ttf}
    return {"type": "PREDICTION_ISSUED", "robot_id": robot_id, "t_s": made_at, "payload": payload}


def scored(events: list[dict]) -> dict:
    """score_run on a temporary run folder: the bearing scenario's answer key + these events."""
    scenario = load_scenario(SCENARIOS_DIR / "bearing_wear_p2_02.json")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        write_ground_truth(build_ground_truth(scenario, configs.load_faults(), "test_run"), folder)
        (folder / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        score = score_run(folder, DETECTOR)
        validate(json.loads((folder / "score.json").read_text()), "score")
    return score


class TestScoring(unittest.TestCase):
    def test_lead_time_arithmetic(self):
        """failure_t_s 12600 and first predictive warning at 10500 -> lead time 2100 s."""
        self.assertEqual(warning_lead_time_s({"failure_t_s": 12600}, {"made_at_t_s": 10500}), 2100.0)
        fault = scored([prediction_event("P2-02", 9000, "bearing_wear", 5000),     # too far away: not a warning
                        prediction_event("P2-02", 10500, "bearing_wear", 3000)])["faults"][0]
        self.assertEqual(fault["warning_lead_time_s"], 2100.0)
        self.assertEqual(fault["failure_time_error_s"], 900.0)
        self.assertTrue(fault["meets_target"])

    def test_missed_fault(self):
        """No predictive warning before failure_t_s -> lead time None and counted as missed."""
        self.assertIsNone(warning_lead_time_s({"failure_t_s": 12600}, None))
        self.assertIsNone(warning_lead_time_s({"failure_t_s": 12600}, {"made_at_t_s": 12700}))
        fault = scored([prediction_event("P2-02", 12700, "bearing_wear", 100)])["faults"][0]
        self.assertTrue(fault["missed"])
        self.assertFalse(fault["meets_target"])

    def test_wrong_diagnosis_is_flagged(self):
        """A first warning naming the wrong fault: diagnosis_correct is False, and the lead
        time only counts the later correct warning."""
        fault = scored([prediction_event("P2-02", 9800, "cooling_fault", 3000),
                        prediction_event("P2-02", 11000, "bearing_wear", 1500)])["faults"][0]
        self.assertFalse(fault["diagnosis_correct"])
        self.assertEqual(fault["first_warning_fault_mode"], "cooling_fault")
        self.assertEqual(fault["warning_lead_time_s"], 1600.0)
        self.assertFalse(fault["meets_target"] if fault["warning_lead_time_s"] < 900 else False)

    def test_unknown_or_unsure_predictions_are_not_warnings(self):
        events = [prediction_event("P2-02", 9000, "unknown", 2000), prediction_event("P2-02", 9100, "bearing_wear", 2000, 0.3)]
        self.assertIsNone(first_predictive_warning(events, "P2-02", DETECTOR))

    def test_false_alarm_count(self):
        """Anomalies, predictive warnings and work orders on robots with no injected fault."""
        events = [{"type": "ANOMALY_RAISED", "robot_id": "P2-01", "t_s": 100, "payload": {"t_s": 100}},
                  prediction_event("P2-03", 500, "wheel_drag", 1000),
                  prediction_event("P2-03", 600, "wheel_drag", 9000),             # not a warning
                  {"type": "WORK_ORDER_CREATED", "robot_id": "P2-04", "t_s": 700, "payload": {}},
                  {"type": "ANOMALY_RAISED", "robot_id": "P2-02", "t_s": 9000, "payload": {"t_s": 9000}}]
        score = scored(events)
        self.assertEqual(score["false_alarms"], {"anomalies": 1, "predictive_warnings": 1, "work_orders": 1})
        self.assertEqual(score["faults"][0]["first_anomaly_t_s"], 9000)
        self.assertEqual(score["faults"][0]["detection_delay_s"], 9000 - 3600)


if __name__ == "__main__":
    unittest.main()
