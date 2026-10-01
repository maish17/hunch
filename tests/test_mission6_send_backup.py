"""Mission 6 - Send in the Backup. STUBS: remove @skip as p4maint/fleet is built.

An active robot develops a serious problem: remove it from service, dispatch it to
P5, pick a standby, put the standby into service, and keep a record of every step.
"""

import unittest

TODO = unittest.skip("TODO(Mission 6): needs p4maint.fleet and p4maint.pipeline")


class TestMission6SendInTheBackup(unittest.TestCase):
    @TODO
    def test_failing_robot_leaves_service(self):
        """In bearing_wear_p2_02, P2-02 goes ACTIVE -> MAINTENANCE_REQUIRED -> EN_ROUTE_P5
        -> IN_GARAGE, every step a legal transition."""

    @TODO
    def test_standby_chosen_by_the_rule(self):
        """Of the eligible standbys (STANDBY, NORMAL health, SOC >= 60%) the one with the
        highest SOC is chosen; the STANDBY_SELECTED event lists every candidate."""

    @TODO
    def test_replacement_takes_over_the_mission(self):
        """The replacement becomes ACTIVE on M-HAUL-B and the mission stays covered."""

    @TODO
    def test_critical_swaps_immediately_warning_waits(self):
        """CRITICAL orders swap in a standby at creation; WARNING orders keep the robot
        working until it is dispatched (config/dispatch.json swap_in_when)."""

    @TODO
    def test_decision_record_is_complete(self):
        """events.jsonl links prediction -> work order -> status changes -> standby swap
        through refs.caused_by_event_id, and every line validates."""

    @TODO
    def test_no_standby_available(self):
        """With no eligible standby, STANDBY_UNAVAILABLE is logged and the mission shows
        covered = false on the fleet board."""

    @TODO
    def test_garage_full_queues_by_priority(self):
        """Capacity 1 and two orders: the CRITICAL one gets the bay, the WARNING one waits
        at queue position 1."""

    @TODO
    def test_repaired_robot_returns_to_standby_pool(self):
        """After est_repair_s the robot is RETURNED_TO_SERVICE, its fault is cleared in the
        simulator, then STANDBY with standby = true."""


if __name__ == "__main__":
    unittest.main()
