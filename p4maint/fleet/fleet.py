"""Fleet state: who is doing what, and swapping in a standby (Mission 6).

Responsibility: own the fleet_state contract (schemas/fleet_state.schema.json).
Change robot statuses only through set_robot_status() (which uses the state machine
and writes ROBOT_STATUS_CHANGED to the event log), keep the mission roster covered,
and pick a replacement from the standby pool using config/dispatch.json
standby_selection. Every decision is written to the event log with the reason.

STATUS: building and updating the fleet state is done (the dashboard needs it). The
decisions - set_robot_status, select_standby, swap_in_standby - are Mission 6 stubs.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from p4maint.eventlog.log import EventLog
from schemas.validate import validate


def _iso(start_time_utc: str, t_s: float) -> str:
    start = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ")
    return (start + timedelta(seconds=t_s)).strftime("%Y-%m-%dT%H:%M:%SZ")


def initial_fleet_state(scenario: dict) -> dict:
    """fleet_state at t = 0 from the scenario's robots and missions.
    Health starts UNKNOWN with score null until the first snapshot arrives."""
    robots = []
    for robot in scenario["robots"]:
        robots.append({
            "robot_id": robot["robot_id"], "robot_type": robot["robot_type"],
            "status": robot["initial_status"], "status_since_t_s": 0, "mission_id": robot["mission_id"],
            "health_status": "UNKNOWN", "health_score": None, "soc_pct": robot["initial_soc_pct"],
            "location": dict(robot["location"]), "standby": False, "open_work_order_id": None,
        })
    missions = []
    for mission in scenario["missions"]:
        assigned = [r["robot_id"] for r in robots if r["mission_id"] == mission["mission_id"] and r["status"] == "ACTIVE"]
        missions.append({"mission_id": mission["mission_id"], "label": mission["label"],
                         "assigned_robot_id": assigned[0] if assigned else None, "covered": bool(assigned)})
    start = scenario["start_time_utc"]
    return {"schema_version": "1.0.0", "t_s": 0, "generated_at": _iso(start, 0), "robots": robots, "missions": missions}


def get_robot(fleet_state: dict, robot_id: str) -> dict:
    """This robot's entry in fleet_state["robots"]. Raises KeyError if absent."""
    for robot in fleet_state["robots"]:
        if robot["robot_id"] == robot_id:
            return robot
    raise KeyError(f"No robot {robot_id} in the fleet")


def update_health(fleet_state: dict, snapshot: dict, dispatch_cfg: dict) -> None:
    """Copy status, score and SOC from a health snapshot into the robot's entry and
    recompute its standby flag (STANDBY + NORMAL health + SOC >= min_soc_pct). Also moves
    the fleet state's clock to the snapshot's time."""
    robot = get_robot(fleet_state, snapshot["robot_id"])
    robot["health_status"] = snapshot["status"]
    robot["health_score"] = snapshot["health_score"]
    for subsystem in snapshot["subsystems"]:
        for component in subsystem["components"]:
            for channel in component["channels"]:
                if channel["channel"] == "battery_soc_pct" and channel["value"] is not None:
                    robot["soc_pct"] = round(channel["value"], 1)
    rule = dispatch_cfg["standby_selection"]
    robot["standby"] = (robot["status"] in rule["eligible_statuses"]
                        and robot["health_status"] == rule["require_health_status"]
                        and robot["soc_pct"] is not None and robot["soc_pct"] >= rule["min_soc_pct"])
    fleet_state["t_s"] = snapshot["t_s"]
    fleet_state["generated_at"] = snapshot["timestamp"]


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
    validate(fleet_state, "fleet_state")
    path = Path(folder) / "fleet_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fleet_state, indent=2) + "\n")
    return path
