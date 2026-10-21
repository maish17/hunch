"""Robot and work-order state machines (p4maint/fleet/state_machine.py)."""

import unittest

from p4maint import configs
from p4maint.fleet.state_machine import (IllegalTransition, check_robot_transition,
                                         check_work_order_transition, legal_next_robot_states)

SM = configs.load_state_machine()


class TestRobotStateMachine(unittest.TestCase):
    def test_every_listed_transition_is_accepted(self):
        for t in SM["robot"]["transitions"]:
            with self.subTest(move=f"{t['from']} -> {t['to']}"):
                self.assertIsNone(check_robot_transition(t["from"], t["to"], SM))

    def test_unlisted_transition_is_rejected(self):
        for current, new in [("STANDBY", "IN_GARAGE"), ("IN_GARAGE", "ACTIVE"), ("ACTIVE", "EN_ROUTE_P5")]:
            with self.subTest(move=f"{current} -> {new}"):
                with self.assertRaises(IllegalTransition):
                    check_robot_transition(current, new, SM)

    def test_same_state_is_rejected(self):
        with self.assertRaises(IllegalTransition):
            check_robot_transition("ACTIVE", "ACTIVE", SM)

    def test_unknown_state_is_rejected(self):
        with self.assertRaises(IllegalTransition):
            check_robot_transition("ACTIV", "STANDBY", SM)
        with self.assertRaises(IllegalTransition):
            check_robot_transition("ACTIVE", "BROKEN", SM)

    def test_legal_next_states(self):
        self.assertEqual(sorted(legal_next_robot_states("IN_GARAGE", SM)), ["RETURNED_TO_SERVICE"])
        self.assertEqual(sorted(legal_next_robot_states("ACTIVE", SM)), ["DISABLED", "MAINTENANCE_REQUIRED", "STANDBY"])


class TestWorkOrderStateMachine(unittest.TestCase):
    def test_creation_must_start_open(self):
        self.assertIsNone(check_work_order_transition(None, "OPEN", SM))
        with self.assertRaises(IllegalTransition):
            check_work_order_transition(None, "QUEUED", SM)

    def test_happy_path(self):
        path = ["OPEN", "QUEUED", "DISPATCHED", "IN_REPAIR", "COMPLETED"]
        for current, new in zip(path, path[1:]):
            self.assertIsNone(check_work_order_transition(current, new, SM))

    def test_terminal_states_are_final(self):
        for terminal in SM["work_order"]["terminal_states"]:
            for new in SM["work_order"]["states"]:
                if new != terminal:
                    with self.subTest(move=f"{terminal} -> {new}"):
                        with self.assertRaises(IllegalTransition):
                            check_work_order_transition(terminal, new, SM)


if __name__ == "__main__":
    unittest.main()
