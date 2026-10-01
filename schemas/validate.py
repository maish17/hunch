"""Validation helper for every JSON contract in schemas/.

Responsibility: check that a JSON object (or a file of them) matches its contract,
and print readable error messages when it does not. This is plumbing, not
detection logic, so it is implemented now.

Use it from Python:
    from schemas.validate import validate, validate_file
    validate(work_order_dict, "work_order")        # raises ContractError if invalid
    validate_file("fixtures/healthy_fleet/fleet_board.json")

Or from the command line (repo root):
    python schemas/validate.py                     # config, scenarios, all fixtures
    python schemas/validate.py path/to/file.json   # one file, schema guessed from name
"""

import json
import sys
from fnmatch import fnmatch
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCHEMA_DIR.parent

# Which schema a file uses, decided by its file name. First match wins.
SCHEMA_FOR_FILE = [
    ("feed_index.json", "dashboard_index"),
    ("fleet_board.json", "dashboard_fleet_board"),
    ("robot_*.json", "dashboard_robot_detail"),
    ("alerts.json", "dashboard_alerts"),
    ("work_orders.json", "dashboard_work_orders"),
    ("*.jsonl", "event_log_entry"),
    ("channels.json", "channels_config"),
    ("ground_truth*.json", "ground_truth"),
    ("fleet_state*.json", "fleet_state"),
    ("garage_queue*.json", "garage_queue"),
    ("WO-*.json", "work_order"),
    ("work_order*.json", "work_order"),
    ("telemetry_batch*.json", "telemetry_batch"),
    ("health_snapshot*.json", "health_snapshot"),
    ("anomaly_event*.json", "anomaly_event"),
    ("prediction*.json", "prediction"),
    ("scenario*.json", "scenario"),
]


class ContractError(ValueError):
    """Raised when an object does not match its contract."""


_registry_cache = None


def _registry() -> Registry:
    """Load every *.schema.json once so cross-file $refs resolve offline."""
    global _registry_cache
    if _registry_cache is None:
        resources = []
        for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
            schema = json.loads(path.read_text())
            resources.append((schema["$id"], Resource.from_contents(schema)))
        _registry_cache = Registry().with_resources(resources)
    return _registry_cache


def load_schema(name: str) -> dict:
    """Return the schema dict for a contract name such as 'work_order'."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"No schema named '{name}' (looked for {path})")
    return json.loads(path.read_text())


def errors(instance: object, schema_name: str) -> list[str]:
    """Return a list of readable error messages (empty list = valid)."""
    validator = Draft202012Validator(
        load_schema(schema_name), registry=_registry(), format_checker=FormatChecker()
    )
    messages = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        where = "/".join(str(part) for part in error.path) or "(top level)"
        messages.append(f"{where}: {error.message}")
    return messages


def validate(instance: object, schema_name: str) -> None:
    """Raise ContractError listing every problem if instance does not match the schema."""
    problems = errors(instance, schema_name)
    if problems:
        raise ContractError(f"{schema_name}: {len(problems)} problem(s)\n  " + "\n  ".join(problems))


def schema_name_for(path: Path) -> str | None:
    """Guess the contract for a file from its folder or name (see SCHEMA_FOR_FILE)."""
    if path.resolve().parent.name == "scenarios":
        return "scenario"
    name = path.name.replace(".example", "")
    for pattern, schema_name in SCHEMA_FOR_FILE:
        if fnmatch(name, pattern):
            return schema_name
    return None


def validate_file(path: str | Path, schema_name: str | None = None) -> None:
    """Validate a .json file, or every line of a .jsonl file. Raises ContractError."""
    path = Path(path)
    schema_name = schema_name or schema_name_for(path)
    if schema_name is None:
        raise ContractError(f"{path}: cannot tell which schema applies; pass schema_name")
    if path.suffix == ".jsonl":
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if line.strip():
                try:
                    validate(json.loads(line), schema_name)
                except ContractError as err:
                    raise ContractError(f"{path} line {line_number}: {err}") from None
    else:
        try:
            validate(json.loads(path.read_text()), schema_name)
        except ContractError as err:
            raise ContractError(f"{path}: {err}") from None


def default_targets() -> list[Path]:
    """Files checked when the CLI is run with no arguments."""
    targets = [REPO_ROOT / "config" / "channels.json"]
    targets += sorted((REPO_ROOT / "scenarios").glob("*.json"))
    targets += sorted((REPO_ROOT / "fixtures").rglob("*.json"))
    targets += sorted((REPO_ROOT / "fixtures").rglob("*.jsonl"))
    return targets


def main(argv: list[str]) -> int:
    targets = [Path(arg) for arg in argv] if argv else default_targets()
    failures = 0
    for path in targets:
        try:
            validate_file(path)
            print(f"ok    {path.relative_to(REPO_ROOT) if path.is_absolute() else path}")
        except ContractError as err:
            failures += 1
            print(f"FAIL  {err}")
    print(f"\n{len(targets) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
