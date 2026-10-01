"""Robot and work-order state machines (docs/DECISIONS.md section 8).

Responsibility: the single gatekeeper for status changes. Every robot status change
and work-order status change goes through check_*_transition(), which raises
IllegalTransition unless config/state_machine.json lists the move.

STATUS: IllegalTransition is defined; the checks are stubs (a good first task:
about ten lines with a for-loop over the transitions list).
"""


class IllegalTransition(Exception):
    """A status change that config/state_machine.json does not allow."""


def legal_next_robot_states(current: str, state_machine_cfg: dict) -> list[str]:
    """Every state a robot in `current` may move to."""
    raise NotImplementedError("legal_next_robot_states")


def check_robot_transition(current: str, new: str, state_machine_cfg: dict) -> None:
    """Return None if current -> new is legal for a robot, else raise IllegalTransition.

    Also raise for unknown state names, and for current == new (not a transition).
    """
    raise NotImplementedError("check_robot_transition")


def check_work_order_transition(current: str | None, new: str, state_machine_cfg: dict) -> None:
    """Same for work orders. current is None only when creating (new must be OPEN)."""
    raise NotImplementedError("check_work_order_transition")
