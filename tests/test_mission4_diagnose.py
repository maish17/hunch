"""Mission 4 - Diagnose the Robot.

Given different failure signatures, name the most likely fault and subsystem and
assign a severity.
"""

import json
import unittest

from p4maint import configs
from p4maint.analysis import GroundAnalysis
from p4maint.diagnose.diagnosis import choose_fault, score_candidates, severity_for
from tests.streams import CHANNELS, DETECTOR, FAULT_SCENARIOS, MODES, generate, scenario_result, single_robot_scenario, slow

FAULTS = configs.load_faults()


def first_named(result: dict) -> dict:
    """The first prediction that names a fault (not "unknown")."""
    return next(p for p in result["predictions"] if p["fault_mode"] != "unknown")


@slow
class TestMission4WholeScenarios(unittest.TestCase):
    def test_bearing_wear_versus_wheel_drag(self):
        """THE central case. Same current rise and speed drop; only the temperature evidence
        differs. Each scenario must name its own fault and never the other one."""
        bearing, drag = scenario_result("bearing_wear_p2_02"), scenario_result("wheel_drag_p2_01")
        self.assertEqual(bearing["score"]["faults"][0]["first_warning_fault_mode"], "bearing_wear")
        self.assertEqual(drag["score"]["faults"][0]["first_warning_fault_mode"], "wheel_drag")
        self.assertNotIn("wheel_drag", {p["fault_mode"] for p in bearing["predictions"]})
        self.assertNotIn("bearing_wear", {p["fault_mode"] for p in drag["predictions"]})
        self.assertEqual(first_named(bearing)["signature_observed"]["thermal_residual"], "UP")
        self.assertEqual(first_named(drag)["signature_observed"]["thermal_residual"], "NORMAL")

    def test_every_fault_diagnosed_correctly(self):
        for name in FAULT_SCENARIOS:
            with self.subTest(scenario=name):
                result = scenario_result(name)
                fault = result["score"]["faults"][0]
                self.assertTrue(fault["diagnosis_correct"], fault)
                named = {p["fault_mode"] for p in result["predictions"]} - {"unknown"}
                self.assertEqual(named, {fault["fault_type"]}, "a wrong fault was announced")

    def test_correct_component_and_subsystem(self):
        expected = {"bearing_wear_p2_02": ("wheel_fl_drive", "MOBILITY"), "wheel_drag_p2_01": ("wheel_rr_drive", "MOBILITY"),
                    "cooling_fault_p2_03": ("wheel_fr_thermal", "THERMAL"), "battery_degradation_p2_02": ("battery_pack", "POWER")}
        for name, (component, subsystem) in expected.items():
            prediction = first_named(scenario_result(name))
            with self.subTest(scenario=name):
                self.assertEqual((prediction["component"], prediction["subsystem"]), (component, subsystem))

    def test_candidates_ranked_and_scored(self):
        for name in FAULT_SCENARIOS:
            for prediction in scenario_result(name)["predictions"]:
                scores = [c["score"] for c in prediction["candidates"]]
                with self.subTest(scenario=name, prediction=prediction["prediction_id"]):
                    self.assertEqual(len(scores), 4)
                    self.assertEqual(scores, sorted(scores, reverse=True))
                    self.assertTrue(all(0 <= s <= 1 for s in scores))

    def test_half_formed_evidence_is_unknown(self):
        """Before the signature is complete the diagnosis says "unknown", not a guess."""
        first = scenario_result("bearing_wear_p2_02")["predictions"][0]
        self.assertEqual(first["fault_mode"], "unknown")


class TestMission4Rules(unittest.TestCase):
    def test_low_charge_is_not_degradation(self):
        """A healthy robot running its battery nearly flat gets a low-charge alert, but the
        diagnosis never blames battery_degradation (no extra voltage sag is seen)."""
        scenario = single_robot_scenario([("TRAVERSE_LOADED", 600)], 3600)
        scenario["robots"][0]["initial_soc_pct"] = 32.0
        df = generate(scenario)
        analysis = GroundAnalysis({"channels": CHANNELS, "modes": MODES, "faults": FAULTS, "detector": DETECTOR},
                                  scenario["start_time_utc"])
        alerts, named = [], set()
        for _, batch in df.groupby(df["t_s"] // 60):
            result = analysis.analyse_batch(batch)["P2-01"]
            alerts += [a["channel"] for a in result["raised"]]
            if result["prediction"]:
                named.add(result["prediction"]["fault_mode"])
        self.assertIn("battery_soc_pct", alerts)
        self.assertNotIn("battery_degradation", named)

    def test_a_fault_needs_its_own_distinctive_evidence(self):
        """All-normal wheels and an unclear voltage: battery_degradation scores 0.8 by
        elimination but is not named, because its sag is not actually seen."""
        signature = {"wheel_current": "NORMAL", "wheel_speed": "NORMAL", "wheel_temp": "NORMAL",
                     "thermal_residual": "NORMAL", "voltage_residual": "UNCLEAR"}
        candidates = score_candidates(signature, FAULTS)
        self.assertEqual(candidates[0], {"fault_mode": "battery_degradation", "score": 0.8})
        self.assertEqual(choose_fault(candidates, signature, FAULTS, DETECTOR), "unknown")
        signature["voltage_residual"] = "DOWN"
        self.assertEqual(choose_fault(score_candidates(signature, FAULTS), signature, FAULTS, DETECTOR), "battery_degradation")

    def test_each_signature_picks_its_fault(self):
        for fault in FAULTS["faults"]:
            with self.subTest(fault=fault["id"]):
                candidates = score_candidates(fault["signature"], FAULTS)
                self.assertEqual(candidates[0], {"fault_mode": fault["id"], "score": 1.0})
                self.assertEqual(choose_fault(candidates, fault["signature"], FAULTS, DETECTOR), fault["id"])

    def test_tie_is_unknown(self):
        """Early bearing wear: excess heat is clear but the current rise and speed drop are
        not yet. bearing_wear and cooling_fault both score 0.6, so the answer is unknown."""
        signature = {"wheel_current": "UNCLEAR", "wheel_speed": "UNCLEAR", "wheel_temp": "UP",
                     "thermal_residual": "UP", "voltage_residual": "NORMAL"}
        candidates = score_candidates(signature, FAULTS)
        self.assertEqual(candidates[0]["score"], candidates[1]["score"])
        self.assertEqual(choose_fault(candidates, signature, FAULTS, DETECTOR), "unknown")

    def test_severity_rules(self):
        """CRITICAL if ttf < 30 min or a channel is already CRITICAL; otherwise the fault's
        consequence_severity from config/faults.json; unknown faults are WARNING."""
        self.assertEqual(severity_for("wheel_drag", 5000, False, FAULTS, DETECTOR), "WARNING")
        self.assertEqual(severity_for("wheel_drag", 1000, False, FAULTS, DETECTOR), "CRITICAL")
        self.assertEqual(severity_for("wheel_drag", None, True, FAULTS, DETECTOR), "CRITICAL")
        self.assertEqual(severity_for("bearing_wear", 5000, False, FAULTS, DETECTOR), "CRITICAL")
        self.assertEqual(severity_for("unknown", None, False, FAULTS, DETECTOR), "WARNING")



EXPECTED_ON_BOARD = {"bearing_wear_p2_02": ("P2-02", "bearing wear"), "wheel_drag_p2_01": ("P2-01", "wheel drag"),
                     "cooling_fault_p2_03": ("P2-03", "cooling fault"), "battery_degradation_p2_02": ("P2-02", "battery degradation")}


def board_row(folder, robot_id: str) -> dict:
    board = json.loads((folder / "fleet_board.json").read_text())
    return [r for r in board["robots"] if r["robot_id"] == robot_id][0]


@slow
class TestMission4OnTheDashboard(unittest.TestCase):
    def test_shown_on_fleet_board(self):
        """Mission 4: the suspected fault is displayed on the fleet-health dashboard. At the
        end of every fault run the faulty robot's headline names its fault. (Its readings
        may be NORMAL at that instant if it happens to be parked.)"""
        for name, (robot_id, words) in EXPECTED_ON_BOARD.items():
            with self.subTest(scenario=name):
                self.assertIn(words, board_row(scenario_result(name)["dashboard"], robot_id)["headline"].lower())


class TestMission4OnTheWebsiteDemo(unittest.TestCase):
    def test_website_snapshots_show_the_fault(self):
        """The committed demo data (make site-data) shows each faulty robot WARNING or worse,
        with its fault named, and every other robot NORMAL."""
        from p4maint.paths import REPO_ROOT
        for name, (robot_id, words) in EXPECTED_ON_BOARD.items():
            folder = REPO_ROOT / "site" / "demo" / "generated" / name
            row = board_row(folder, robot_id)
            with self.subTest(scenario=name):
                self.assertIn(row["health_status"], ("WARNING", "CRITICAL"))
                self.assertIn(words, row["headline"].lower())
                board = json.loads((folder / "fleet_board.json").read_text())
                others = {r["health_status"] for r in board["robots"] if r["robot_id"] != robot_id}
                self.assertEqual(others, {"NORMAL"})


if __name__ == "__main__":
    unittest.main()
