"""Mission 5 - Generate the Work Order. STUBS: remove @skip as p4maint/workorders is built.

Automatically create a work order (robot ID, suspected failure, evidence, severity,
recommended action, predicted time-to-failure), set the robot to
MAINTENANCE_REQUIRED and place it in the P5 queue.
"""

import unittest

TODO = unittest.skip("TODO(Mission 5): needs p4maint.workorders and p4maint.fleet")


class TestMission5GenerateTheWorkOrder(unittest.TestCase):
    @TODO
    def test_work_order_contains_required_fields_and_validates(self):
        """create_work_order() output passes schemas/work_order.schema.json and has robot id,
        suspected failure, severity, recommended action and predicted_ttf_s."""

    @TODO
    def test_recommended_action_comes_from_config(self):
        """recommended_action equals the fault's entry in config/faults.json."""

    @TODO
    def test_telemetry_evidence_embedded(self):
        """evidence.channels has the target channel with <= 61 points at 60 s spacing."""

    @TODO
    def test_robot_becomes_maintenance_required(self):
        """Robot status ACTIVE -> MAINTENANCE_REQUIRED, with a ROBOT_STATUS_CHANGED event."""

    @TODO
    def test_work_order_enters_garage_queue(self):
        """Status OPEN -> QUEUED and the order appears in garage_queue.queue."""

    @TODO
    def test_one_open_work_order_per_robot(self):
        """A second qualifying prediction for the same robot creates no second order."""

    @TODO
    def test_id_format_and_sequence(self):
        """Ids are WO-<YYYYMMDD>-<NNNN> and increase by one per order."""

    @TODO
    def test_history_is_append_only(self):
        """set_status appends a history entry and never edits earlier ones."""


if __name__ == "__main__":
    unittest.main()
