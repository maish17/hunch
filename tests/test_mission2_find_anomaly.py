"""Mission 2 - Find the Anomaly. STUBS: remove @skip as p4maint/detect is built.

One abnormal condition in an otherwise healthy stream must be detected
automatically, attributed to its subsystem, timestamped, and alerted.
"""

import unittest

TODO = unittest.skip("TODO(Mission 2): needs p4maint.detect.anomaly")


class TestMission2FindTheAnomaly(unittest.TestCase):
    @TODO
    def test_rising_motor_current(self):
        """Ramp wheel_fl_current_a past its WARNING offset -> exactly one anomaly_event on
        that channel, component wheel_fl_drive, subsystem MOBILITY."""

    @TODO
    def test_excessive_temperature(self):
        """Drive temperature past baseline + 15 degC -> anomaly on wheel_*_temp_c, subsystem THERMAL."""

    @TODO
    def test_unusual_wheel_speed(self):
        """Wheel speed below baseline - 0.08 rad/s -> anomaly on wheel_*_speed_rads (MOBILITY)."""

    @TODO
    def test_declining_battery_voltage(self):
        """Voltage sag beyond -0.5 V of the battery model -> anomaly on battery_voltage_v (POWER)."""

    @TODO
    def test_event_timestamp_is_when_it_started(self):
        """anomaly t_s is the first sample past the limit; detected_t_s is the batch end."""

    @TODO
    def test_single_noisy_sample_is_ignored(self):
        """One spike shorter than persistence_samples raises nothing."""

    @TODO
    def test_no_repeat_alerts(self):
        """A condition that stays bad raises one event, not one per batch (realert_suppress_s)."""

    @TODO
    def test_escalation_raises_new_event(self):
        """WARNING then CRITICAL on the same channel -> two events, second severity CRITICAL."""

    @TODO
    def test_alert_reaches_operator_feed(self):
        """An ANOMALY_RAISED event is logged and appears in the alerts feed newest first."""

    @TODO
    def test_healthy_run_raises_nothing(self):
        """scenarios/healthy_baseline.json end to end -> zero anomalies (false positives waste P5)."""


if __name__ == "__main__":
    unittest.main()
