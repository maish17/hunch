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
from p4maint.analysis import GroundAnalysis
from p4maint.dashboard_export import feeds
from p4maint.eventlog.log import EventLog
from p4maint.fleet import fleet as fleet_ops
from p4maint.fleet import garage as garage_ops
from p4maint.generator.ground_truth import build_ground_truth, write_ground_truth
from p4maint.generator.scenario import load_scenario, make_run_id
from p4maint.generator.simulate import FleetSimulator
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
    # ... and the ground system's state. GroundAnalysis does Missions 1-4 (the same code
    # p4maint/openloop.py runs today).
    state = {
        "writer": open_store(paths.telemetry_path(folder), cfg["channels"]),
        "analysis": GroundAnalysis(cfg, start),
        "events": EventLog(paths.events_path(folder), start),
        "fleet": fleet_ops.initial_fleet_state(scenario),
        "garage": garage_ops.new_garage(cfg["dispatch"], scenario.get("garage_capacity"), 0, start),
        "work_orders": {},     # work_order_id -> work order dict
        "predictions": {},     # robot_id -> latest prediction dict
        "snapshots": {},       # robot_id -> latest health snapshot
        "minutes": {},         # robot_id -> dashboard minute points (feeds.minute_point)
        "anomalies": [],       # every anomaly raised
        "published": [],       # every prediction announced, in order
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
        now_t_s = int(batch["t_s"].max())

        for robot_id, result in state["analysis"].analyse_batch(batch).items():
            state["snapshots"][robot_id] = result["snapshot"]
            state["minutes"].setdefault(robot_id, []).append(feeds.minute_point(result["evaluated"]))
            state["anomalies"].extend(result["raised"])
            if result["published"]:
                state["published"].append(result["prediction"])
            fleet_ops.update_health(state["fleet"], result["snapshot"], cfg["dispatch"])
            act_on_findings(robot_id, result, now_t_s, state, cfg, start)

        advance_fleet_and_garage(now_t_s, sim, state, cfg, start, run_id)
        if (now_t_s + 1) % cfg["dispatch"]["dashboard_export"]["refresh_every_s"] == 0:
            publish(folder, run_id, scenario, now_t_s, state, cfg)

    # 5. Finish, score, and write the final dashboard feeds.
    close_store(state["writer"])
    state["events"].append("RUN_FINISHED", now_t_s, None, f"Run {run_id} finished", {})
    score_run(folder, cfg["detector"])
    publish(folder, run_id, scenario, now_t_s, state, cfg)
    return folder


def open_work_order_severities(state: dict) -> dict[str, str]:
    """{robot_id: severity} for robots with an open work order (the simulator needs it
    to decide whether a MAINTENANCE_REQUIRED robot keeps working)."""
    raise NotImplementedError("pipeline.open_work_order_severities")


def act_on_findings(robot_id: str, result: dict, now_t_s: int, state: dict, cfg: dict, start: str) -> None:
    """Log what GroundAnalysis found for one robot, then act on it (Mission 5).

    TODO(pipeline owner), in this order:
      1. log ANOMALY_RAISED / ANOMALY_CLEARED for result["raised"] / result["cleared"], and
         PREDICTION_ISSUED when result["published"] (copy p4maint/openloop.py, which does
         exactly this today); keep result["prediction"] in state["predictions"]
      2. workorders.workorder.should_create(...) -> create_work_order(...), set_status to
         QUEUED, garage.enqueue(...), fleet set_robot_status MAINTENANCE_REQUIRED,
         log everything; if severity is CRITICAL, fleet.swap_in_standby(...) now
    """
    raise NotImplementedError("pipeline.act_on_findings")


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
    """Write every dashboard feed to runs/<run_id>/dashboard/ (same export as make detect)."""
    feeds.export_run(paths.dashboard_dir(folder), run_id, scenario, now_t_s, state["fleet"], state["garage"],
                     list(state["work_orders"].values()), state["snapshots"], state["minutes"], state["anomalies"],
                     state["published"], state["events"].read_all(), cfg,
                     f"Run {run_id} (closed loop) at {now_t_s} s")

