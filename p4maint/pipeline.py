"""Run one scenario end to end. Called by run_scenario.py.

Responsibility: wiring only. Load configs, write the answer key, then loop one
60 s batch at a time:

    simulate -> check + store -> evaluate health -> detect anomalies
             -> diagnose + predict -> work orders -> fleet / garage -> dashboard feeds

and finally score the run. Each stage lives in its own package; this file only
calls them in order, so reading it top to bottom is the architecture.

While stages are still stubs the run stops at the first NotImplementedError and
run_scenario.py reports which stage it reached. That is expected.
"""

import shutil
from pathlib import Path

from p4maint import paths
from p4maint.configs import (load_channels, load_detector_params, load_dispatch, load_faults,
                             load_generator_params, load_modes, load_state_machine)
from p4maint.dashboard_export import feeds  # used by publish() once implemented
from p4maint.detect.anomaly import AnomalyDetector
from p4maint.eventlog.log import EventLog
from p4maint.fleet import fleet as fleet_ops
from p4maint.fleet import garage as garage_ops
from p4maint.generator.ground_truth import build_ground_truth, write_ground_truth
from p4maint.generator.scenario import load_scenario, make_run_id
from p4maint.generator.simulate import FleetSimulator
from p4maint.health.evaluate import build_snapshot, evaluate_samples, new_baseline_state
from p4maint.ingest.history import RollingWindow
from p4maint.ingest.store import append_batch, check_batch, close_store, open_store
from p4maint.scoring.lead_time import score_run


def prepare_run_folder(run_id: str) -> Path:
    """Fresh runs/<run_id>/ with its sub-folders. Deletes a previous run of the same id
    (runs are reproducible from the seed, so nothing is lost)."""
    folder = paths.run_dir(run_id)
    if folder.exists():
        assert paths.RUNS_DIR in folder.parents, "refusing to delete outside runs/"
        shutil.rmtree(folder)
    for sub in [paths.state_dir(folder), paths.work_orders_dir(folder), paths.dashboard_dir(folder)]:
        sub.mkdir(parents=True)
    return folder


def run(scenario_path: Path) -> Path:
    """Run a scenario; return the run folder."""
    # 1. Load. Every number the code uses comes from these files.
    scenario = load_scenario(scenario_path)
    cfg = {
        "channels": load_channels(), "modes": load_modes(), "faults": load_faults(),
        "detector": load_detector_params(), "state_machine": load_state_machine(),
        "dispatch": load_dispatch(),
    }
    run_id = make_run_id(scenario)
    folder = prepare_run_folder(run_id)
    start = scenario["start_time_utc"]

    # 2. Answer key, written by the generator side before anything else runs.
    #    Only scoring reads it back (tests/test_answer_key_isolation.py).
    write_ground_truth(build_ground_truth(scenario, cfg["faults"], run_id), folder)

    # 3. The simulated world (generator only sees generator.json) ...
    sim = FleetSimulator(scenario, load_generator_params(), cfg["modes"], cfg["faults"],
                         cfg["channels"], cfg["state_machine"])
    # ... and the ground system's state.
    look_back_s = max(cfg["detector"]["trend"]["fit_window_s"],
                      cfg["dispatch"]["work_order_evidence"]["window_s"])
    state = {
        "writer": open_store(paths.telemetry_path(folder), cfg["channels"]),
        "telemetry": RollingWindow(look_back_s),
        "evaluated": RollingWindow(look_back_s),
        "baselines": new_baseline_state(),
        "detector": AnomalyDetector(cfg["detector"], cfg["channels"], start),
        "events": EventLog(paths.events_path(folder), start),
        "fleet": fleet_ops.initial_fleet_state(scenario),
        "garage": garage_ops.new_garage(cfg["dispatch"], scenario.get("garage_capacity"), 0, start),
        "work_orders": {},     # work_order_id -> work order dict
        "predictions": {},     # robot_id -> latest prediction dict
        "snapshots": {},       # robot_id -> latest health snapshot
    }
    state["events"].append("RUN_STARTED", 0, None, f"Run {run_id} started", {"scenario_id": scenario["scenario_id"]})

    # 4. Main loop: one batch per pass.
    now_t_s = 0
    while not sim.finished():
        batch = sim.step(state["fleet"], open_work_order_severities(state))
        problems = check_batch(batch, cfg["channels"])
        if problems:
            raise ValueError("Bad telemetry batch: " + "; ".join(problems))
        append_batch(state["writer"], batch, cfg["channels"])
        state["telemetry"].add(batch)
        now_t_s = int(batch["t_s"].max())

        for robot_id in sorted(batch["robot_id"].unique()):
            rows = batch[batch["robot_id"] == robot_id]
            evaluated = evaluate_samples(rows, robot_id, cfg["channels"], cfg["modes"], cfg["detector"],
                                         state["baselines"])
            evaluated["robot_id"] = robot_id
            state["evaluated"].add(evaluated)
            snapshot = build_snapshot(evaluated, robot_id, cfg["channels"], cfg["detector"], start)
            state["snapshots"][robot_id] = snapshot
            fleet_ops.update_health(state["fleet"], snapshot, cfg["dispatch"])
            analyse_robot(robot_id, now_t_s, state, cfg, start)

        advance_fleet_and_garage(now_t_s, sim, state, cfg, start, run_id)
        publish(folder, run_id, scenario, now_t_s, state, cfg)

    # 5. Finish and score.
    close_store(state["writer"])
    state["events"].append("RUN_FINISHED", now_t_s, None, f"Run {run_id} finished", {})
    score_run(folder, cfg["detector"])
    return folder


def open_work_order_severities(state: dict) -> dict[str, str]:
    """{robot_id: severity} for robots with an open work order (the simulator needs it
    to decide whether a MAINTENANCE_REQUIRED robot keeps working)."""
    raise NotImplementedError("pipeline.open_work_order_severities")


def analyse_robot(robot_id: str, now_t_s: int, state: dict, cfg: dict, start: str) -> None:
    """Missions 2-5 for one robot after its batch has been evaluated.

    TODO(pipeline owner), in this order:
      1. state["detector"].update(...) -> log ANOMALY_RAISED / ANOMALY_CLEARED
      2. diagnose.diagnosis.diagnose(...) on the look-back windows
      3. predict.trend.trend_for_channel(...) on the diagnosis target channel
      4. predict.prediction.build_prediction(...) -> log PREDICTION_ISSUED (only when it
         changes materially, not every batch)
      5. workorders.workorder.should_create(...) -> create_work_order(...), set_status to
         QUEUED, garage.enqueue(...), fleet set_robot_status MAINTENANCE_REQUIRED,
         log everything; if severity is CRITICAL, fleet.swap_in_standby(...) now
    """
    raise NotImplementedError("pipeline.analyse_robot")


def advance_fleet_and_garage(now_t_s: int, sim: FleetSimulator, state: dict, cfg: dict, start: str,
                             run_id: str) -> None:
    """Mission 6 bookkeeping once per batch.

    TODO(pipeline owner):
      - garage.reserve_next(...) while a bay is free -> work order DISPATCHED, robot
        EN_ROUTE_P5 (swap in a standby now if it was WARNING and still on a mission)
      - robots whose eta has passed -> garage.admit(...), IN_REPAIR, IN_GARAGE
      - bays whose est_release_t_s has passed -> garage.release(...), COMPLETED,
        RETURNED_TO_SERVICE, sim.repair(robot_id), then STANDBY
      - save fleet_state, garage_queue and changed work orders under the run folder
    """
    raise NotImplementedError("pipeline.advance_fleet_and_garage")


def publish(folder: Path, run_id: str, scenario: dict, now_t_s: int, state: dict, cfg: dict) -> None:
    """Build every dashboard feed with p4maint.dashboard_export.feeds and write them to
    runs/<run_id>/dashboard/ (feeds.write_all)."""
    raise NotImplementedError("pipeline.publish")

