"""Mission 3 - Catch It Before It Breaks.

Recognise a developing trend and warn BEFORE the failure threshold. Headline metric:
warning lead time, measured against the answer key by p4maint/scoring.
"""

import unittest

import numpy as np

from p4maint.predict.prediction import is_predictive_warning, should_publish
from p4maint.predict.trend import fit_linear_trend, time_to_threshold, trends_for_robot
from schemas.validate import validate
from tests.streams import (CHANNELS, DETECTOR, FAULT_SCENARIOS, MODES, analyse, generate, scenario_result,
                           single_robot_scenario, slow)

TARGET_S = DETECTOR["predictive_warning"]["target_lead_time_s"]


@slow
class TestMission3WholeScenarios(unittest.TestCase):
    def test_bearing_wear_warned_at_least_15_minutes_early(self):
        """bearing_wear_p2_02: score.json lead time >= 900 s (true failure at 12600 s, so the
        first correct predictive warning must come by 11700 s)."""
        fault = scenario_result("bearing_wear_p2_02")["score"]["faults"][0]
        self.assertTrue(fault["meets_target"], fault)
        self.assertGreaterEqual(fault["warning_lead_time_s"], TARGET_S)
        self.assertLessEqual(fault["first_warning_t_s"], 12600 - TARGET_S)

    def test_every_fault_type_warned_at_least_15_minutes_early(self):
        for name in FAULT_SCENARIOS:
            with self.subTest(scenario=name):
                fault = scenario_result(name)["score"]["faults"][0]
                self.assertTrue(fault["meets_target"], fault)
                self.assertFalse(fault["missed"])

    def test_warning_precedes_critical_status(self):
        """The first predictive warning comes before any CRITICAL alert on that robot."""
        for name in FAULT_SCENARIOS:
            result = scenario_result(name)
            fault = result["score"]["faults"][0]
            critical = [a["t_s"] for a in result["anomalies"] if a["robot_id"] == fault["robot_id"] and a["severity"] == "CRITICAL"]
            with self.subTest(scenario=name):
                if critical:
                    self.assertLess(fault["first_warning_t_s"], min(critical))

    def test_ttf_estimate_and_interval_reported(self):
        """Every prediction with a time-to-failure has low <= ttf <= high, a failure time of
        made_at + ttf, and validates against the contract."""
        for name in FAULT_SCENARIOS:
            for prediction in scenario_result(name)["predictions"]:
                validate(prediction, "prediction")
                ttf = prediction["predicted_ttf_s"]
                if ttf is None:
                    continue
                interval = prediction["predicted_ttf_interval_s"]
                with self.subTest(scenario=name, prediction=prediction["prediction_id"]):
                    self.assertLessEqual(interval["low"], ttf + 1e-6)
                    self.assertGreaterEqual(interval["high"], ttf - 1e-6)
                    self.assertAlmostEqual(prediction["predicted_failure_t_s"], prediction["made_at_t_s"] + ttf, delta=1)

    def test_healthy_run_has_no_predictions(self):
        self.assertEqual(scenario_result("healthy_baseline")["predictions"], [])

    def test_predictions_are_not_repeated_needlessly(self):
        """Consecutive announcements for a robot always differ in something that matters."""
        for name in FAULT_SCENARIOS:
            published = scenario_result(name)["predictions"]
            for previous, new in zip(published, published[1:]):
                with self.subTest(scenario=name, prediction=new["prediction_id"]):
                    self.assertTrue(should_publish(previous, new, DETECTOR))


class TestMission3TrendMaths(unittest.TestCase):
    def test_linear_fit_recovers_a_line(self):
        t = np.arange(0, 1800.0)
        fit = fit_linear_trend(t, 2.0 + 0.01 * t)
        self.assertAlmostEqual(fit["slope_per_s"], 0.01)
        self.assertAlmostEqual(fit["intercept_at_end"], 2.0 + 0.01 * 1799)
        self.assertAlmostEqual(fit["r_squared"], 1.0)
        self.assertIsNone(fit_linear_trend(np.array([1.0, 2.0]), np.array([1.0, 2.0])))

    def test_time_to_threshold_arithmetic(self):
        """Deviation 10 rising 0.005/s toward a +30 limit -> 4000 s, inside its interval."""
        trend = {"slope_per_s": 0.005, "intercept_at_end": 10.0, "slope_stderr": 0.0005, "n_points": 1800, "r_squared": 0.9}
        ttf = time_to_threshold(trend, 30.0, DETECTOR, "high")
        self.assertAlmostEqual(ttf["ttf_s"], 4000.0)
        self.assertLess(ttf["low_s"], 4000.0)
        self.assertGreater(ttf["high_s"], 4000.0)

    def test_trend_away_from_limit_is_ignored(self):
        """A falling temperature never gets a time-to-failure on its high limit."""
        trend = {"slope_per_s": -0.005, "intercept_at_end": 10.0, "slope_stderr": 0.0005, "n_points": 1800, "r_squared": 0.9}
        self.assertIsNone(time_to_threshold(trend, 30.0, DETECTOR, "high"))

    def test_already_past_the_limit_is_zero(self):
        trend = {"slope_per_s": 0.005, "intercept_at_end": 31.0, "slope_stderr": 0.0005, "n_points": 1800, "r_squared": 0.9}
        self.assertEqual(time_to_threshold(trend, 30.0, DETECTOR, "high")["ttf_s"], 0.0)
        soc_falling = {"slope_per_s": -0.001, "intercept_at_end": 12.0, "slope_stderr": 0.0001, "n_points": 1800, "r_squared": 0.9}
        self.assertEqual(time_to_threshold(soc_falling, 15.0, DETECTOR, "low")["ttf_s"], 0.0)

    def test_crossing_beyond_horizon_is_ignored(self):
        trend = {"slope_per_s": 0.0001, "intercept_at_end": 0.0, "slope_stderr": 0.00001, "n_points": 1800, "r_squared": 0.9}
        self.assertIsNone(time_to_threshold(trend, 30.0, DETECTOR, "high"))


class TestMission3NoFalseTrends(unittest.TestCase):
    def test_flat_signal_gives_no_trend(self):
        evaluated = analyse(generate(single_robot_scenario([("TRAVERSE_EMPTY", 600)], 3600)))["evaluated"]
        self.assertEqual(trends_for_robot(evaluated, CHANNELS, MODES, DETECTOR, 3599), [])

    def test_mode_changes_are_not_a_trend(self):
        """Raw current steps between empty and loaded driving; the deviation-based trend
        sees nothing toward a CRITICAL limit."""
        evaluated = analyse(generate(single_robot_scenario([("TRAVERSE_EMPTY", 600), ("TRAVERSE_LOADED", 600)], 3600)))["evaluated"]
        self.assertEqual(trends_for_robot(evaluated, CHANNELS, MODES, DETECTOR, 3599), [])


class TestPredictiveWarningRule(unittest.TestCase):
    def test_rule(self):
        base = {"predicted_ttf_s": 3000.0, "fault_mode": "bearing_wear", "confidence": 1.0}
        self.assertTrue(is_predictive_warning(base, DETECTOR))
        self.assertFalse(is_predictive_warning(dict(base, predicted_ttf_s=4000.0), DETECTOR))
        self.assertFalse(is_predictive_warning(dict(base, predicted_ttf_s=None), DETECTOR))
        self.assertFalse(is_predictive_warning(dict(base, fault_mode="unknown"), DETECTOR))
        self.assertFalse(is_predictive_warning(dict(base, confidence=0.4), DETECTOR))


if __name__ == "__main__":
    unittest.main()
