"""Mission 2 - Find the Anomaly.

One abnormal condition in an otherwise healthy stream must be detected
automatically, attributed to its subsystem, timestamped, and alerted.
"""

import json
import unittest

from schemas.validate import validate
from tests.streams import add_ramp, analyse, generate, scenario_result, single_robot_scenario, slow

RAMP_START = 900


def events_for(result: dict, channel: str) -> list[dict]:
    return [event for event in result["raised"] if event["channel"] == channel]


class TestMission2InjectedConditions(unittest.TestCase):
    """Each test adds one abnormal condition to the same healthy hour of TRAVERSE_EMPTY driving."""

    @classmethod
    def setUpClass(cls):
        cls.healthy = generate(single_robot_scenario([("TRAVERSE_EMPTY", 600)], 3600))

    def check_single_warning(self, channel: str, per_s: float, cap: float, limit: float, subsystem: str, component: str):
        result = analyse(add_ramp(self.healthy, channel, RAMP_START, per_s, cap))
        self.assertEqual([(e["channel"], e["severity"]) for e in result["raised"]], [(channel, "WARNING")])
        event = result["raised"][0]
        validate(event, "anomaly_event")
        self.assertEqual(event["subsystem"], subsystem)
        self.assertEqual(event["component"], component)
        crossing_t_s = RAMP_START + limit / per_s
        self.assertLess(abs(event["t_s"] - crossing_t_s), 25, "start time should be when the limit was crossed")
        return event

    def test_rising_motor_current(self):
        self.check_single_warning("wheel_fl_current_a", 0.01, 1.5, 1.0, "MOBILITY", "wheel_fl_drive")

    def test_excessive_temperature(self):
        self.check_single_warning("wheel_rl_temp_c", 0.05, 20.0, 15.0, "THERMAL", "wheel_rl_thermal")

    def test_unusual_wheel_speed(self):
        self.check_single_warning("wheel_fr_speed_rads", -0.001, -0.12, -0.08, "MOBILITY", "wheel_fr_drive")

    def test_declining_battery_voltage(self):
        self.check_single_warning("battery_voltage_v", -0.002, -0.8, -0.5, "POWER", "battery_pack")

    def test_event_timestamp_is_when_it_started(self):
        """t_s is the first sample past the limit; detected_t_s is the end of the batch it was confirmed in."""
        event = self.check_single_warning("wheel_rl_temp_c", 0.05, 20.0, 15.0, "THERMAL", "wheel_rl_thermal")
        self.assertGreaterEqual(event["detected_t_s"], event["t_s"])
        self.assertEqual(event["detected_t_s"] % 60, 59)
        self.assertLess(event["detected_t_s"] - event["t_s"], 120)
        self.assertGreater(event["magnitude"], 15.0)
        self.assertIn("rear-left drive temperature", event["message"])

    def test_single_noisy_sample_is_ignored(self):
        """A 3-sample spike (a sensor glitch) raises nothing: smoothing + persistence."""
        glitch = self.healthy.copy()
        mask = (glitch["t_s"] >= 1200) & (glitch["t_s"] < 1203)
        glitch.loc[mask, "wheel_fl_current_a"] = glitch.loc[mask, "wheel_fl_current_a"] + 5.0
        self.assertEqual(analyse(glitch)["raised"], [])

    def test_no_repeat_alerts(self):
        """A condition that stays bad for 40 minutes raises one event, not one per batch."""
        result = analyse(add_ramp(self.healthy, "wheel_fl_current_a", RAMP_START, 0.01, 1.5))
        self.assertEqual(len(events_for(result, "wheel_fl_current_a")), 1)

    def test_escalation_raises_new_event(self):
        """WARNING then CRITICAL on the same channel -> two events, the second CRITICAL."""
        result = analyse(add_ramp(self.healthy, "wheel_fl_current_a", RAMP_START, 0.01, 2.5))
        severities = [e["severity"] for e in events_for(result, "wheel_fl_current_a")]
        self.assertEqual(severities, ["WARNING", "CRITICAL"])

    def test_clears_and_suppresses_repeats(self):
        """Bad, normal, bad again within 10 min -> no second alert; bad again later -> alert."""
        df = self.healthy.copy()
        for start, end in [(900, 1200), (1300, 1600), (2400, 2700)]:  # 2nd starts 400 s after the 1st
            mask = (df["t_s"] >= start) & (df["t_s"] < end)
            df.loc[mask, "wheel_fl_current_a"] = df.loc[mask, "wheel_fl_current_a"] + 1.5
        result = analyse(df)
        starts = [e["t_s"] for e in events_for(result, "wheel_fl_current_a")]
        self.assertEqual(len(starts), 2, starts)
        self.assertLess(abs(starts[0] - 900), 20)
        self.assertLess(abs(starts[1] - 2400), 20)
        self.assertGreaterEqual(len(result["cleared"]), 2)

    def test_healthy_hour_raises_nothing(self):
        self.assertEqual(analyse(self.healthy)["raised"], [])


@slow
class TestMission2WholeScenarios(unittest.TestCase):
    """The real acceptance tests: whole scenarios, every robot, open loop."""

    @classmethod
    def setUpClass(cls):
        cls.healthy = scenario_result("healthy_baseline")
        cls.bearing = scenario_result("bearing_wear_p2_02")

    def test_healthy_run_raises_nothing(self):
        """scenarios/healthy_baseline.json: zero anomalies (false positives waste P5) and
        every robot ends NORMAL."""
        self.assertEqual(self.healthy["anomalies"], [])
        self.assertEqual({s["status"] for s in self.healthy["snapshots"].values()}, {"NORMAL"})

    def test_bearing_wear_is_caught_on_the_right_wheel_before_failure(self):
        """Only P2-02 is flagged; the first alert is its front-left temperature, at least
        15 min before the scheduled failure at 12600 s."""
        anomalies = self.bearing["anomalies"]
        self.assertTrue(anomalies)
        self.assertEqual({e["robot_id"] for e in anomalies}, {"P2-02"})
        self.assertEqual({e["component"] for e in anomalies}, {"wheel_fl_drive", "wheel_fl_thermal"})
        first = anomalies[0]
        self.assertEqual((first["channel"], first["subsystem"]), ("wheel_fl_temp_c", "THERMAL"))
        self.assertGreaterEqual(12600 - first["t_s"], 900)

    def test_alert_is_logged_for_the_operator(self):
        """Every alert is an ANOMALY_RAISED line in events.jsonl with the full event as payload."""
        lines = [json.loads(line) for line in (self.bearing["folder"] / "events.jsonl").read_text().splitlines()]
        for line in lines:
            validate(line, "event_log_entry")
        raised = [line for line in lines if line["type"] == "ANOMALY_RAISED"]
        self.assertEqual(len(raised), len(self.bearing["anomalies"]))
        for line in raised:
            validate(line["payload"], "anomaly_event")
            self.assertEqual(line["refs"]["anomaly_id"], line["payload"]["anomaly_id"])
        self.assertEqual(lines[0]["type"], "RUN_STARTED")
        self.assertEqual(lines[-1]["type"], "RUN_FINISHED")


if __name__ == "__main__":
    unittest.main()
