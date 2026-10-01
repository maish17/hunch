"""Fleet state: who is doing what, and swapping in a standby (Mission 6).

Responsibility: own the fleet_state contract (schemas/fleet_state.schema.json).
Change robot statuses only through set_robot_status() (which uses the state machine
and writes ROBOT_STATUS_CHANGED to the event log), keep the mission roster covered,
and pick a replacement from the standby pool using config/dispatch.json
standby_selection. Every decision is written to the event log with the reason.

STATUS: stubs. This is Mission 6 logic for the team to write.
"""

from pathlib import Path

from p4maint.eventlog.log import EventLog


def initial_fleet_state(scenario: dict) -> dict:
    """fleet_state at t = 0 from the scenario's robots and missions.
    Health starts UNKNOWN with score null until the first snapshot arrives."""
    raise NotImplementedError("initial_fleet_state")


def get_robot(fleet_state: dict, robot_id: str) -> dict:
    """This robot's entry in fleet_state["robots"]. Raises KeyError if absent."""
    raise NotImplementedError("get_robot")


def update_health(fleet_state: dict, snapshot: dict, dispatch_cfg: dict) -> None:
    """Copy status, score and SOC from a health snapshot into the robot's entry and
    recompute its standby flag (STANDBY + NORMAL health + SOC >= min_soc_pct)."""
    raise NotImplementedError("update_health")


def set_robot_status(fleet_state: dict, robot_id: str, new_status: str, now_t_s: int, reason: str,
                     state_machine_cfg: dict, event_log: EventLog) -> None:
    """Change one robot's status (checked by state_machine.check_robot_transition),
    update status_since_t_s and location zone, and log ROBOT_STATUS_CHANGED."""
    raise NotImplementedError("set_robot_status")


def select_standby(fleet_state: dict, dispatch_cfg: dict) -> tuple[str | None, list[dict]]:
    """(chosen robot_id or None, every candidate considered with its SOC and eligibility).

    The candidate list goes into the STANDBY_SELECTED event so the decision can be
    audited later.
    """
    raise NotImplementedError("select_standby")


def swap_in_standby(fleet_state: dict, failing_robot_id: str, now_t_s: int, dispatch_cfg: dict,
                    state_machine_cfg: dict, event_log: EventLog) -> str | None:
    """Take the failing robot's mission, give it to the best standby, log STANDBY_SELECTED,
    ROBOT_STATUS_CHANGED and MISSION_REASSIGNED (or STANDBY_UNAVAILABLE). Returns the
    replacement's robot_id or None."""
    raise NotImplementedError("swap_in_standby")


def save_fleet_state(fleet_state: dict, folder: Path) -> Path:
    """Validate, then write <folder>/fleet_state.json. Returns the path."""
    raise NotImplementedError("save_fleet_state")
