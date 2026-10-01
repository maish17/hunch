"""Where things live on disk.

Responsibility: every file path in the project is built here, so no other module
glues folder names together by hand. The answer-key path is deliberately NOT here;
it lives in p4maint/generator/ground_truth.py so detector code has no easy way to it.

Layout of one run (runs/<run_id>/):
    telemetry.parquet           all robots, all samples
    events.jsonl                append-only event log
    state/fleet_state.json      latest fleet state
    state/garage_queue.json     latest garage queue
    work_orders/WO-*.json       one file per work order
    dashboard/                  feed files the dashboard reads
    answer_key/ground_truth.json   written by the generator, read only by scoring
    score.json                  lead-time metrics from scoring
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
SCHEMA_DIR = REPO_ROOT / "schemas"
FIXTURES_DIR = REPO_ROOT / "fixtures"
SCENARIOS_DIR = REPO_ROOT / "scenarios"
RUNS_DIR = REPO_ROOT / "runs"


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def telemetry_path(run_folder: Path) -> Path:
    return run_folder / "telemetry.parquet"


def events_path(run_folder: Path) -> Path:
    return run_folder / "events.jsonl"


def state_dir(run_folder: Path) -> Path:
    return run_folder / "state"


def work_orders_dir(run_folder: Path) -> Path:
    return run_folder / "work_orders"


def dashboard_dir(run_folder: Path) -> Path:
    return run_folder / "dashboard"


def score_path(run_folder: Path) -> Path:
    return run_folder / "score.json"
