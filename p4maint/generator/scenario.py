"""Scenario files: load, check, and name runs.

Responsibility: read a scenario JSON file (format: docs/DECISIONS.md section 9,
contract: schemas/scenario.schema.json) and refuse bad ones early with a clear
message. Loading and run naming are plumbing and are implemented; the
cross-reference check is a TODO.
"""

from pathlib import Path

from p4maint.configs import load_generator_params, load_json
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
    """Return a list of problems the schema cannot catch (empty list = fine).

    TODO(generator owner): check that
      - every robot's mission_id (if not null) is defined in scenario["missions"]
      - ACTIVE robots have a mission, STANDBY robots do not
      - robot_ids are unique, and no two ACTIVE robots share a mission
      - every fault's robot_id exists, and its component matches the fault's
        component_pattern in config/faults.json (e.g. wheel_fl_drive for bearing_wear)
      - inject_at_s < duration_s
    """
    raise NotImplementedError("check_scenario_references")
