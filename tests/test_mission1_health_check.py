"""Mission 1 - Robot Health Check. STUBS: remove @skip as p4maint/health is built.

Feed telemetry from a simulated robot and label every measurement (battery level,
motor current, temperature, wheel speed, joint status) NORMAL, WARNING or CRITICAL.
"""

import unittest

TODO = unittest.skip("TODO(Mission 1): needs p4maint.health.evaluate")


class TestMission1HealthCheck(unittest.TestCase):
    @TODO
    def test_every_channel_gets_a_status(self):
        """A healthy TRAVERSE_EMPTY batch -> a snapshot with all 17 channels, every one NORMAL."""

    @TODO
    def test_snapshot_validates_against_contract(self):
        """build_snapshot() output passes schemas/health_snapshot.schema.json."""

    @TODO
    def test_loaded_cargo_is_not_an_alarm(self):
        """Healthy TRAVERSE_LOADED data (current about 4.8 A) is NORMAL. A flat threshold set
        for empty driving would fire here; the mode baseline must prevent that."""

    @TODO
    def test_cool_down_after_driving_is_not_an_alarm(self):
        """Switch TRAVERSE_LOADED -> IDLE: drive temperature stays above the IDLE steady
        state for ~30 min while cooling. The lagged (thermal_lag) baseline keeps it NORMAL."""

    @TODO
    def test_warning_and_critical_offsets(self):
        """wheel_fl_current_a at baseline + 1.0 A -> WARNING (RELATIVE_WARNING_HIGH);
        at baseline + 2.0 A -> CRITICAL. Values come from config/channels.json, not the test."""

    @TODO
    def test_hard_limit_is_critical_in_every_mode(self):
        """A drive temperature of 90 degC is CRITICAL (HARD_CRITICAL_HIGH) even in a mode
        whose baseline + offsets would allow it."""

    @TODO
    def test_low_battery_level(self):
        """battery_soc_pct 25 -> WARNING, 10 -> CRITICAL (absolute limits)."""

    @TODO
    def test_missing_value_is_unknown(self):
        """A null sensor value gives status UNKNOWN with rule NO_DATA, not NORMAL."""

    @TODO
    def test_rollup_worst_status_wins(self):
        """One WARNING channel makes its component, subsystem and robot WARNING; the other
        subsystems stay NORMAL. health_score follows detector.json health_score."""

    @TODO
    def test_joint_status_reported(self):
        """lift_joint_current_a and lift_joint_pos_err_deg appear under MECHANISMS with a
        status in every mode (HUNCH 'joint status')."""


if __name__ == "__main__":
    unittest.main()
