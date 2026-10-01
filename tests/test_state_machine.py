"""Robot and work-order state machines. STUBS: remove @skip once
p4maint/fleet/state_machine.py is written (a good first task)."""

import unittest

TODO = unittest.skip("TODO: needs p4maint.fleet.state_machine")


class TestRobotStateMachine(unittest.TestCase):
    @TODO
    def test_every_listed_transition_is_accepted(self):
        """check_robot_transition() returns None for every pair in config/state_machine.json."""

    @TODO
    def test_unlisted_transition_is_rejected(self):
        """STANDBY -> IN_GARAGE and IN_GARAGE -> ACTIVE raise IllegalTransition."""

    @TODO
    def test_same_state_is_rejected(self):
        """ACTIVE -> ACTIVE raises IllegalTransition (it is not a transition)."""

    @TODO
    def test_unknown_state_is_rejected(self):
        """A misspelt state such as 'ACTIV' raises IllegalTransition."""


class TestWorkOrderStateMachine(unittest.TestCase):
    @TODO
    def test_creation_must_start_open(self):
        """None -> OPEN is accepted; None -> QUEUED is rejected."""

    @TODO
    def test_terminal_states_are_final(self):
        """COMPLETED and CANCELLED cannot move anywhere."""


if __name__ == "__main__":
    unittest.main()
