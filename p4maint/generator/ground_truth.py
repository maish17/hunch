"""The answer key: injected fault type, injection time and TRUE failure time.

Responsibility: build and write runs/<run_id>/answer_key/ground_truth.json
(contract: schemas/ground_truth.schema.json). It is known in full before the run
starts, because the scenario fixes when each fault is injected and how fast it
grows.

ISOLATION RULE: only this module writes the answer key and only p4maint/scoring
reads it. Health, detect, predict, diagnose, workorders, fleet and
dashboard_export must never import this module or open that folder.
tests/test_answer_key_isolation.py enforces it.

STATUS: answer_key_path is implemented (a path); the rest are stubs.
"""

from pathlib import Path

ANSWER_KEY_FOLDER = "answer_key"


def answer_key_path(run_folder: Path) -> Path:
    return run_folder / ANSWER_KEY_FOLDER / "ground_truth.json"


def build_ground_truth(scenario: dict, faults_cfg: dict, run_id: str) -> dict:
    """Answer-key dict for a scenario.

    TODO(generator owner): one entry per scenario fault with
      inject_t_s  = inject_at_s
      failure_t_s = inject_at_s + time_to_failure_s   (the moment p reaches 1)
      primary_channel from faults.primary_channel(), subsystem from config/faults.json,
      progression (scenario override or default), generator_parameter and
      parameter_at_failure from the fault's generator_effect,
      and ISO timestamps from scenario["start_time_utc"].
    Set "warning" to the exact const in the schema.
    """
    raise NotImplementedError("build_ground_truth")


def write_ground_truth(ground_truth: dict, run_folder: Path) -> Path:
    """Validate against schemas/ground_truth.schema.json, then write it. Returns the path.

    TODO(generator owner): schemas.validate.validate(ground_truth, "ground_truth"),
    create the answer_key folder, write with indent=2.
    """
    raise NotImplementedError("write_ground_truth")
