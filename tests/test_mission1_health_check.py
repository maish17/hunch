"""Mission 1 - Robot Health Check.

Feed telemetry from a simulated robot and label every measurement (battery level,
motor current, temperature, wheel speed, joint status) NORMAL, WARNING or CRITICAL.
"""

import unittest

from p4maint import configs
from p4maint.health.evaluate import classify, health_score, rollup
from schemas.validate import validate
from tests.streams import CHANNELS, DETECTOR, START, analyse, generate, single_robot_scenario

from p4maint.health.evaluate import build_snapshot


def channel(name: str) -> dict:
    return configs.get_channel(CHANNELS, name)


class TestMission1OnSimulatedData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty = analyse(generate(single_robot_scenario([("TRAVERSE_EMPTY", 600)], 1800)))
        cls.loaded = analyse(generate(single_robot_scenario([("TRAVERSE_LOADED", 600)], 1800)))
        cls.cool_down = analyse(generate(single_robot_scenario([("TRAVERSE_LOADED", 2400), ("IDLE", 1800)], 4200)))
        cls.handling = analyse(generate(single_robot_scenario([("CARGO_HANDLING", 300), ("TRAVERSE_EMPTY", 300)], 1200)))

    def test_every_channel_gets_a_status(self):
        """A healthy TRAVERSE_EMPTY run -> a snapshot with all 17 channels, every one NORMAL."""
        snapshot = self.empty["snapshot"]
        entries = [ch for sub in snapshot["subsystems"] for comp in sub["components"] for ch in comp["channels"]]
        self.assertEqual(sorted(e["channel"] for e in entries), sorted(configs.channel_names(CHANNELS)))
        self.assertEqual({e["status"] for e in entries}, {"NORMAL"})
        self.assertEqual(snapshot["status"], "NORMAL")
        self.assertEqual(snapshot["health_score"], 100)

    def test_snapshot_validates_against_contract(self):
        validate(self.empty["snapshot"], "health_snapshot")

    def test_loaded_cargo_is_not_an_alarm(self):
        """Healthy TRAVERSE_LOADED data (current about 4.8 A) stays NORMAL, although a flat
        limit set for empty driving (3.29 + 1.0 A) would fire on it."""
        evaluated = self.loaded["evaluated"]
        self.assertEqual(set(evaluated["status"]), {"NORMAL"})
        current = evaluated[(evaluated["channel"] == "wheel_fl_current_a") & (evaluated["t_s"] > 60)]
        flat_limit = configs.load_modes()["modes"][1]["baselines"]["wheel_fl_current_a"] + channel("wheel_fl_current_a")["limits"]["warning_high"]
        self.assertGreater(current["value"].median(), flat_limit)

    def test_cool_down_after_driving_is_not_an_alarm(self):
        """TRAVERSE_LOADED -> IDLE: the drive stays above the IDLE steady state for ~30 min
        while cooling. The lagged (thermal_lag) baseline keeps it NORMAL."""
        evaluated = self.cool_down["evaluated"]
        self.assertEqual(set(evaluated["status"]), {"NORMAL"})
        # First minute after stopping: far enough above the IDLE steady state that a
        # non-lagged baseline would call it a WARNING.
        just_stopped = evaluated[(evaluated["channel"] == "wheel_fl_temp_c") & (evaluated["t_s"].between(2430, 2490))]
        idle_steady_state = [m for m in configs.load_modes()["modes"] if m["id"] == "IDLE"][0]["baselines"]["wheel_fl_temp_c"]
        warning_offset = channel("wheel_fl_temp_c")["limits"]["warning_high"]
        self.assertGreater(just_stopped["value"].min() - idle_steady_state, warning_offset)

    def test_joint_status_reported(self):
        """Lift channels appear under MECHANISMS with a status, in CARGO_HANDLING and other modes."""
        evaluated = self.handling["evaluated"]
        lift = evaluated[evaluated["channel"].isin(["lift_joint_current_a", "lift_joint_pos_err_deg"])]
        self.assertEqual(set(lift["op_mode"]), {"CARGO_HANDLING", "TRAVERSE_EMPTY"})
        self.assertEqual(set(lift["status"]), {"NORMAL"})
        mechanisms = [s for s in self.handling["snapshot"]["subsystems"] if s["subsystem"] == "MECHANISMS"][0]
        self.assertEqual({c["channel"] for c in mechanisms["components"][0]["channels"]},
                         {"lift_joint_current_a", "lift_joint_pos_err_deg"})

    def test_rollup_worst_status_wins(self):
        """One WARNING channel makes its component, subsystem and robot WARNING; the other
        subsystems stay NORMAL; health_score follows detector.json."""
        evaluated = self.empty["evaluated"].copy()
        last = evaluated["t_s"].max()
        mask = (evaluated["t_s"] == last) & (evaluated["channel"] == "wheel_rr_temp_c")
        evaluated.loc[mask, "status"] = "WARNING"
        evaluated.loc[mask, "rule"] = "RELATIVE_WARNING_HIGH"
        snapshot = build_snapshot(evaluated, "P2-01", CHANNELS, DETECTOR, START)
        statuses = {s["subsystem"]: s["status"] for s in snapshot["subsystems"]}
        self.assertEqual(statuses, {"MOBILITY": "NORMAL", "THERMAL": "WARNING", "POWER": "NORMAL", "MECHANISMS": "NORMAL"})
        thermal = [s for s in snapshot["subsystems"] if s["subsystem"] == "THERMAL"][0]
        rr = [c for c in thermal["components"] if c["component"] == "wheel_rr_thermal"][0]
        self.assertEqual(rr["status"], "WARNING")
        self.assertEqual(snapshot["status"], "WARNING")
        self.assertEqual(snapshot["health_score"], DETECTOR["health_score"]["status_points"]["WARNING"])


class TestMission1Rules(unittest.TestCase):
    """The status rule itself. Limits come from config/channels.json, never from the test."""

    def test_warning_and_critical_offsets(self):
        current = channel("wheel_fl_current_a")
        base = 3.29
        self.assertEqual(classify(base, current, base), ("NORMAL", None))
        self.assertEqual(classify(base + current["limits"]["warning_high"], current, base), ("WARNING", "RELATIVE_WARNING_HIGH"))
        self.assertEqual(classify(base + current["limits"]["critical_high"], current, base), ("CRITICAL", "RELATIVE_CRITICAL_HIGH"))
        speed = channel("wheel_fl_speed_rads")
        self.assertEqual(classify(2.25 + speed["limits"]["warning_low"], speed, 2.25), ("WARNING", "RELATIVE_WARNING_LOW"))

    def test_hard_limit_is_critical_in_every_mode(self):
        """90 degC is CRITICAL even when baseline + offsets would allow it."""
        temp = channel("wheel_fl_temp_c")
        hard = temp["hard_limits"]["critical_high"]
        self.assertEqual(classify(hard, temp, hard - 5), ("CRITICAL", "HARD_CRITICAL_HIGH"))
        self.assertEqual(classify(hard, temp, hard - 5, skip_relative=True), ("CRITICAL", "HARD_CRITICAL_HIGH"))

    def test_mode_change_grace_skips_relative_but_not_hard(self):
        current = channel("wheel_fl_current_a")
        self.assertEqual(classify(5.0, current, 0.0, skip_relative=True), ("NORMAL", None))
        self.assertEqual(classify(9.0, current, 0.0, skip_relative=True), ("CRITICAL", "HARD_CRITICAL_HIGH"))

    def test_low_battery_level(self):
        soc = channel("battery_soc_pct")
        self.assertEqual(classify(25.0, soc, None), ("WARNING", "ABSOLUTE_WARNING_LOW"))
        self.assertEqual(classify(10.0, soc, None), ("CRITICAL", "ABSOLUTE_CRITICAL_LOW"))
        self.assertEqual(classify(80.0, soc, None), ("NORMAL", None))

    def test_missing_value_is_unknown(self):
        self.assertEqual(classify(float("nan"), channel("wheel_fl_current_a"), 3.29), ("UNKNOWN", "NO_DATA"))
        self.assertEqual(classify(None, channel("battery_soc_pct"), None), ("UNKNOWN", "NO_DATA"))

    def test_rollup_and_score(self):
        self.assertEqual(rollup([]), "NORMAL")
        self.assertEqual(rollup(["NORMAL", "UNKNOWN"]), "UNKNOWN")
        self.assertEqual(rollup(["UNKNOWN", "WARNING", "NORMAL"]), "WARNING")
        self.assertEqual(rollup(["WARNING", "CRITICAL"]), "CRITICAL")
        self.assertEqual(health_score({"A": "NORMAL", "B": "CRITICAL"}, DETECTOR), 20)
        self.assertIsNone(health_score({"A": "UNKNOWN"}, DETECTOR))


if __name__ == "__main__":
    unittest.main()
