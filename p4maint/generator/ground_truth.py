"""The answer key: injected fault type, injection time and TRUE failure time.

Responsibility: build and write runs/<run_id>/answer_key/ground_truth.json
(contract: schemas/ground_truth.schema.json). It is known in full before the run
starts, because the scenario fixes when each fault is injected and how fast it
grows.

ISOLATION RULE: only this module writes the answer key and only p4maint/scoring
reads it. Health, detect, predict, diagnose, workorders, fleet and
dashboard_export must never import this module or open that folder.
tests/test_answer_key_isolation.py enforces it.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from p4maint.configs import get_fault
from p4maint.generator.faults import primary_channel
from schemas.validate import validate

ANSWER_KEY_FOLDER = "answer_key"
WARNING_TEXT = "ANSWER KEY - must never be read by detection, prediction or diagnosis code."


def answer_key_path(run_folder: Path) -> Path:
    return run_folder / ANSWER_KEY_FOLDER / "ground_truth.json"


def iso_utc(start_time_utc: str, t_s: float) -> str:
    """ISO 8601 UTC timestamp (trailing Z) for t_s seconds after the scenario start."""
    moment = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=t_s)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_ground_truth(scenario: dict, faults_cfg: dict, run_id: str) -> dict:
    """Answer-key dict for a scenario.

    One entry per scenario fault: inject_t_s = inject_at_s, failure_t_s =
    inject_at_s + time_to_failure_s (the moment progress p reaches 1), the primary
    channel, the progression actually used, and the generator parameter it drives.
    """
    start = scenario["start_time_utc"]
    entries = []
    for fault in scenario["faults"]:
        fault_def = get_fault(faults_cfg, fault["fault_type"])
        failure_t_s = fault["inject_at_s"] + fault["time_to_failure_s"]
        entries.append({
            "fault_id": fault["fault_id"],
            "robot_id": fault["robot_id"],
            "fault_type": fault["fault_type"],
            "component": fault["component"],
            "subsystem": fault_def["subsystem"],
            "primary_channel": primary_channel(fault_def, fault["component"]),
            "inject_t_s": fault["inject_at_s"],
            "inject_at": iso_utc(start, fault["inject_at_s"]),
            "failure_t_s": failure_t_s,
            "failure_at": iso_utc(start, failure_t_s),
            "progression": fault.get("progression", fault_def["default_progression"]),
            "generator_parameter": fault_def["generator_effect"]["parameter"],
            "parameter_at_failure": fault_def["generator_effect"]["at_failure"],
        })
    return {
        "schema_version": "1.0.0",
        "scenario_id": scenario["scenario_id"],
        "run_id": run_id,
        "seed": scenario["seed"],
        "start_time_utc": start,
        "duration_s": scenario["duration_s"],
        "faults": entries,
        "warning": WARNING_TEXT,
    }


def write_ground_truth(ground_truth: dict, run_folder: Path) -> Path:
    """Validate against schemas/ground_truth.schema.json, then write it. Returns the path."""
    validate(ground_truth, "ground_truth")
    path = answer_key_path(run_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ground_truth, indent=2) + "\n")
    return path
