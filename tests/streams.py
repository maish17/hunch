"""Test helpers: build telemetry streams and push them through health + anomaly detection
one 60 s batch at a time, exactly as the pipeline will."""

import pandas as pd

from p4maint import configs
from p4maint.detect.anomaly import AnomalyDetector
from p4maint.generator.scenario import load_scenario
from p4maint.generator.simulate import FleetSimulator, open_loop_fleet_state
from p4maint.health.evaluate import build_snapshot, evaluate_samples, new_baseline_state
from p4maint.paths import SCENARIOS_DIR

CHANNELS = configs.load_channels()
MODES = configs.load_modes()
DETECTOR = configs.load_detector_params()
START = "2027-03-01T00:00:00Z"


def single_robot_scenario(mode_cycle: list[tuple[str, int]], duration_s: int, seed: int = 7) -> dict:
    """One ACTIVE robot (P2-01) repeating mode_cycle, e.g. [("TRAVERSE_EMPTY", 600)]."""
    scenario = load_scenario(SCENARIOS_DIR / "healthy_baseline.json")
    scenario.update({"seed": seed, "duration_s": duration_s, "faults": []})
    scenario["missions"] = [{"mission_id": "M-TEST", "label": "test",
                             "mode_cycle": [{"mode": m, "duration_s": d} for m, d in mode_cycle]}]
    robot = dict(scenario["robots"][0], mission_id="M-TEST")
    scenario["robots"] = [robot]
    return scenario


def generate(scenario: dict) -> pd.DataFrame:
    """Whole scenario, open loop, as one DataFrame."""
    sim = FleetSimulator(scenario, configs.load_generator_params(), MODES, configs.load_faults(), CHANNELS,
                         configs.load_state_machine())
    fleet = open_loop_fleet_state(scenario)
    batches = []
    while not sim.finished():
        batches.append(sim.step(fleet, {}))
    return pd.concat(batches, ignore_index=True)


def analyse(df: pd.DataFrame, robot_id: str = "P2-01") -> dict:
    """Evaluate + detect batch by batch. Returns evaluated (all samples), the last
    snapshot, every snapshot's status, and the raised / cleared anomalies."""
    baselines = new_baseline_state()
    detector = AnomalyDetector(DETECTOR, CHANNELS, START)
    rows = df[df["robot_id"] == robot_id]
    evaluated_parts, raised, cleared, statuses = [], [], [], []
    snapshot = None
    for _, batch in rows.groupby(rows["t_s"] // 60):
        evaluated = evaluate_samples(batch, robot_id, CHANNELS, MODES, DETECTOR, baselines)
        snapshot = build_snapshot(evaluated, robot_id, CHANNELS, DETECTOR, START)
        statuses.append(snapshot["status"])
        new, gone = detector.update(evaluated, robot_id, int(batch["t_s"].max()))
        raised.extend(new)
        cleared.extend(gone)
        evaluated_parts.append(evaluated)
    return {"evaluated": pd.concat(evaluated_parts, ignore_index=True), "snapshot": snapshot,
            "statuses": statuses, "raised": raised, "cleared": cleared, "detector": detector}


def add_ramp(df: pd.DataFrame, channel: str, start_t_s: int, per_s: float, cap: float | None = None,
             robot_id: str = "P2-01") -> pd.DataFrame:
    """Inject an abnormal condition: add per_s * (t - start) to one channel after start_t_s
    (optionally held at cap). Returns a new DataFrame."""
    out = df.copy()
    mask = (out["robot_id"] == robot_id) & (out["t_s"] >= start_t_s)
    extra = (out.loc[mask, "t_s"] - start_t_s) * per_s
    if cap is not None:
        extra = extra.clip(upper=cap) if per_s > 0 else extra.clip(lower=cap)
    out.loc[mask, channel] = (out.loc[mask, channel] + extra).astype("float32")
    return out


# ---- Whole-scenario runs, shared by every test module (each runs once per test session) ----

import os
import tempfile
import unittest
from pathlib import Path

from p4maint import openloop

FAULT_SCENARIOS = ["bearing_wear_p2_02", "wheel_drag_p2_01", "cooling_fault_p2_03", "battery_degradation_p2_02"]
_RESULTS: dict[str, dict] = {}
_TMP = tempfile.TemporaryDirectory()

# Whole-scenario tests take about 20 s per scenario. `make test-fast` (P4_FAST=1) skips them.
slow = unittest.skipIf(os.environ.get("P4_FAST") == "1", "P4_FAST=1: skipping whole-scenario runs")


def scenario_result(name: str) -> dict:
    """openloop.run() on scenarios/<name>.json in a temporary folder, cached."""
    if name not in _RESULTS:
        _RESULTS[name] = openloop.run(SCENARIOS_DIR / f"{name}.json", write_telemetry=False,
                                      folder=Path(_TMP.name) / name)
    return _RESULTS[name]
