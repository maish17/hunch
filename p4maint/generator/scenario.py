"""Scenario files: load, check, and name runs.

Responsibility: read a scenario JSON file (format: docs/DECISIONS.md section 9,
contract: schemas/scenario.schema.json) and refuse bad ones early with a clear
message.
"""

from pathlib import Path

from p4maint.configs import get_fault, load_generator_params, load_json
from schemas.validate import validate


def load_scenario(path: str | Path) -> dict:
    """Read and schema-validate a scenario file. Raises ContractError if invalid."""
    scenario = load_json(Path(path))
    validate(scenario, "scenario")
    batch_s = load_generator_params()["timing"]["batch_s"]
    if scenario["duration_s"] % batch_s != 0:
        raise ValueError(f"duration_s must be a multiple of {batch_s} s, got {scenario['duration_s']}")
    return scenario


def make_run_id(scenario: dict) -> str:
    """Deterministic run id, so re-running a scenario overwrites the same folder."""
    return f"{scenario['scenario_id']}__seed{scenario['seed']}"


def check_scenario_references(scenario: dict, channels_cfg: dict, faults_cfg: dict) -> list[str]:
    """Return a list of problems the schema cannot catch (empty list = fine)."""
    problems = []
    mission_ids = {mission["mission_id"] for mission in scenario["missions"]}
    component_ids = {component["id"] for component in channels_cfg["hierarchy"]["components"]}
    robot_ids = [robot["robot_id"] for robot in scenario["robots"]]
    if len(robot_ids) != len(set(robot_ids)):
        problems.append("robot_ids are not unique")

    missions_taken = {}
    for robot in scenario["robots"]:
        robot_id, mission_id = robot["robot_id"], robot["mission_id"]
        if robot["initial_status"] == "ACTIVE" and mission_id is None:
            problems.append(f"{robot_id} is ACTIVE but has no mission")
        if robot["initial_status"] == "STANDBY" and mission_id is not None:
            problems.append(f"{robot_id} is STANDBY but has mission {mission_id}")
        if mission_id is not None and mission_id not in mission_ids:
            problems.append(f"{robot_id} has unknown mission {mission_id}")
        if mission_id is not None and robot["initial_status"] == "ACTIVE":
            if mission_id in missions_taken:
                problems.append(f"{robot_id} and {missions_taken[mission_id]} are both ACTIVE on {mission_id}")
            missions_taken[mission_id] = robot_id

    for fault in scenario["faults"]:
        label = fault["fault_id"]
        if fault["robot_id"] not in robot_ids:
            problems.append(f"{label}: unknown robot {fault['robot_id']}")
        if fault["component"] not in component_ids:
            problems.append(f"{label}: unknown component {fault['component']}")
        pattern = get_fault(faults_cfg, fault["fault_type"])["component_pattern"]
        allowed = {pattern.replace("{wheel}", wheel) for wheel in ("fl", "fr", "rl", "rr")}
        if fault["component"] not in allowed:
            problems.append(f"{label}: {fault['fault_type']} cannot be injected into {fault['component']} (expected {pattern})")
        if fault["inject_at_s"] >= scenario["duration_s"]:
            problems.append(f"{label}: inject_at_s is after the scenario ends")
    return problems
