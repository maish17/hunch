"""Robot and work-order state machines (docs/DECISIONS.md section 8).

Responsibility: the single gatekeeper for status changes. Every robot status change
and work-order status change goes through check_*_transition(), which raises
IllegalTransition unless config/state_machine.json lists the move.
"""


class IllegalTransition(Exception):
    """A status change that config/state_machine.json does not allow."""


def _check(machine: dict, current: str, new: str, kind: str) -> None:
    """Shared rule for both machines: known states, a real change, and a listed move."""
    states = machine["states"]
    if current not in states:
        raise IllegalTransition(f"Unknown {kind} state '{current}'")
    if new not in states:
        raise IllegalTransition(f"Unknown {kind} state '{new}'")
    if current == new:
        raise IllegalTransition(f"{kind} is already {current}; staying put is not a transition")
    for transition in machine["transitions"]:
        if transition["from"] == current and transition["to"] == new:
            return
    raise IllegalTransition(f"{kind} cannot go from {current} to {new} (not listed in config/state_machine.json)")


def legal_next_robot_states(current: str, state_machine_cfg: dict) -> list[str]:
    """Every state a robot in `current` may move to."""
    next_states = []
    for transition in state_machine_cfg["robot"]["transitions"]:
        if transition["from"] == current:
            next_states.append(transition["to"])
    return next_states


def check_robot_transition(current: str, new: str, state_machine_cfg: dict) -> None:
    """Return None if current -> new is legal for a robot, else raise IllegalTransition.

    Also raises for unknown state names, and for current == new (not a transition).
    """
    _check(state_machine_cfg["robot"], current, new, "robot")


def check_work_order_transition(current: str | None, new: str, state_machine_cfg: dict) -> None:
    """Same for work orders. current is None only when creating (new must be OPEN)."""
    machine = state_machine_cfg["work_order"]
    if current is None:
        if new not in machine["initial_states"]:
            raise IllegalTransition(f"A new work order must start in {machine['initial_states']}, not {new}")
        return
    _check(machine, current, new, "work order")
