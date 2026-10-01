"""Mission 4 - Diagnose the Robot. STUBS: remove @skip as p4maint/diagnose is built.

Given different failure signatures, name the most likely fault and subsystem,
assign a severity, and show it on the fleet board.
"""

import unittest

TODO = unittest.skip("TODO(Mission 4): needs p4maint.diagnose")


class TestMission4DiagnoseTheRobot(unittest.TestCase):
    @TODO
    def test_bearing_wear_versus_wheel_drag(self):
        """THE central case. Two windows with the same current rise and speed drop on
        wheel_fl: one with excess heat (thermal residual > 5 degC) -> bearing_wear, one whose
        temperature rise is explained by current -> wheel_drag."""

    @TODO
    def test_cooling_fault(self):
        """Temperature climbing with normal current and speed -> cooling_fault on wheel_*_thermal (THERMAL)."""

    @TODO
    def test_battery_degradation(self):
        """Voltage residual worsening under load, wheels normal -> battery_degradation (POWER)."""

    @TODO
    def test_low_charge_is_not_degradation(self):
        """Low SOC with a normal voltage residual is NOT diagnosed as battery_degradation."""

    @TODO
    def test_correct_wheel_is_localised(self):
        """A fault on wheel_rr is attributed to wheel_rr_*, not another wheel."""

    @TODO
    def test_candidates_ranked_and_scored(self):
        """candidates lists all four faults, best first, scores in [0, 1]."""

    @TODO
    def test_weak_evidence_is_unknown(self):
        """Below detector.json diagnosis.min_confidence the fault_mode is 'unknown'."""

    @TODO
    def test_severity_rules(self):
        """CRITICAL if ttf < 1800 s or a channel is CRITICAL; otherwise the fault's
        consequence_severity from config/faults.json."""

    @TODO
    def test_shown_on_fleet_board(self):
        """The fleet_board feed row for the robot has health WARNING/CRITICAL and a headline
        naming the suspected fault."""


if __name__ == "__main__":
    unittest.main()
