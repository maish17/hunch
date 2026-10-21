"""Open-loop run: generator -> store -> health -> anomalies -> diagnosis + prediction -> score.

    python -m p4maint.openloop scenarios/bearing_wear_p2_02.json      (or: make detect)

Runs every stage that exists today (Missions 1-4 and scoring) on one scenario,
before the fleet manager is built. OPEN LOOP: robots keep their starting status and
mission the whole run, so nobody is sent to P5 and no standby is swapped in. The
full closed-loop run is run_scenario.py.

Writes runs/<run_id>__open_loop/:
    telemetry.parquet, answer_key/ground_truth.json   (same as make generate)
    events.jsonl        RUN_STARTED, ANOMALY_RAISED/CLEARED, PREDICTION_ISSUED, RUN_FINISHED
    state/health_<ROBOT>.json   last health snapshot per robot
    state/fleet_state.json, state/garage_queue.json
    dashboard/          feed files for dashboard/ (open it with the URL the run prints)
    score.json          lead time etc. vs the answer key (p4maint/scoring, the only reader of it)

Work orders and the standby swap (Missions 5-6) are not built yet, so the fleet keeps
its starting statuses and the garage stays empty in these feeds.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from p4maint import configs, paths
from p4maint.analysis import GroundAnalysis
from p4maint.dashboard_export.feeds import component_name, export_run, minute_point
from p4maint.eventlog.log import EventLog
from p4maint.fleet.fleet import initial_fleet_state, save_fleet_state, update_health
from p4maint.fleet.garage import new_garage, save_garage
from p4maint.generator.ground_truth import build_ground_truth, write_ground_truth
from p4maint.generator.scenario import check_scenario_references, load_scenario, make_run_id
from p4maint.generator.simulate import FleetSimulator, open_loop_fleet_state
from p4maint.ingest.store import append_batch, check_batch, close_store, open_store
from p4maint.predict.prediction import is_predictive_warning
from p4maint.scoring.lead_time import score_run
from schemas.validate import validate


def run(scenario_path: Path, write_telemetry: bool = True, folder: Path | None = None,
        dashboard_folder: Path | None = None, dashboard_at_t_s: int | None = None) -> dict:
    """Run the scenario. Returns {"folder", "dashboard", "scenario", "anomalies", "cleared",
    "predictions", "snapshots", "score"}. folder defaults to runs/<run_id>__open_loop/
    (tests pass a temporary folder); dashboard_folder defaults to <folder>/dashboard
    (make site-data points it at site/demo/generated/<scenario_id>). The feeds show the
    fleet at the end of the run, or at the first batch ending at or after dashboard_at_t_s."""
    cfg = {"channels": configs.load_channels(), "modes": configs.load_modes(),
           "faults": configs.load_faults(), "detector": configs.load_detector_params(),
           "state_machine": configs.load_state_machine(), "dispatch": configs.load_dispatch()}
    scenario = load_scenario(scenario_path)
    problems = check_scenario_references(scenario, cfg["channels"], cfg["faults"])
    if problems:
        raise ValueError("Scenario problems:\n  " + "\n  ".join(problems))

    run_id = make_run_id(scenario)
    if folder is None:
        folder = paths.run_dir(run_id + "__open_loop")
        if folder.exists():
            assert paths.RUNS_DIR in folder.parents, "refusing to delete outside runs/"
            shutil.rmtree(folder)
    paths.state_dir(folder).mkdir(parents=True, exist_ok=True)
    start = scenario["start_time_utc"]

    write_ground_truth(build_ground_truth(scenario, cfg["faults"], run_id), folder)
    sim = FleetSimulator(scenario, configs.load_generator_params(), cfg["modes"], cfg["faults"],
                         cfg["channels"], configs.load_state_machine())
    fleet_state = open_loop_fleet_state(scenario)
    writer = open_store(paths.telemetry_path(folder), cfg["channels"]) if write_telemetry else None
    events = EventLog(paths.events_path(folder), start)
    analysis = GroundAnalysis(cfg, start)
    anomalies, cleared, predictions, snapshots, minutes = [], [], [], {}, {}
    events.append("RUN_STARTED", 0, None, f"Open-loop run {run_id} started", {"scenario_id": scenario["scenario_id"]})

    dashboard = Path(dashboard_folder) if dashboard_folder else paths.dashboard_dir(folder)
    label = f"Generated run: {scenario['scenario_id']} (seed {scenario['seed']}, open loop)"

    def export_dashboard(at_t_s: int) -> None:
        """Feeds as of at_t_s. Open loop: statuses stay as the scenario set them; no work orders yet."""
        fleet = initial_fleet_state(scenario)
        for snapshot in snapshots.values():
            update_health(fleet, snapshot, cfg["dispatch"])
        garage = new_garage(cfg["dispatch"], scenario.get("garage_capacity"), at_t_s, start)
        save_fleet_state(fleet, paths.state_dir(folder))
        save_garage(garage, paths.state_dir(folder))
        export_run(dashboard, run_id, scenario, at_t_s, fleet, garage, [], snapshots, minutes, anomalies,
                   predictions, events.read_all(), cfg, label)

    exported = False
    now_t_s = 0
    while not sim.finished():
        batch = sim.step(fleet_state, {})
        batch_problems = check_batch(batch, cfg["channels"], cfg["modes"])
        if batch_problems:
            raise ValueError("Bad batch: " + "; ".join(batch_problems))
        if writer:
            append_batch(writer, batch, cfg["channels"])
        now_t_s = int(batch["t_s"].max())
        for robot_id, result in analysis.analyse_batch(batch).items():
            snapshots[robot_id] = result["snapshot"]
            minutes.setdefault(robot_id, []).append(minute_point(result["evaluated"]))
            for event in result["raised"]:
                events.append("ANOMALY_RAISED", now_t_s, robot_id, event["message"], event,
                              {"anomaly_id": event["anomaly_id"]})
            for item in result["cleared"]:
                events.append("ANOMALY_CLEARED", item["t_s"], robot_id,
                              f"{robot_id} {item['channel']} back to NORMAL", item, {"anomaly_id": item["anomaly_id"]})
            if result["published"]:
                prediction = result["prediction"]
                events.append("PREDICTION_ISSUED", now_t_s, robot_id, prediction_summary(prediction, cfg), prediction,
                              {"prediction_id": prediction["prediction_id"]})
                predictions.append(prediction)
            anomalies.extend(result["raised"])
            cleared.extend(result["cleared"])
        if dashboard_at_t_s is not None and not exported and now_t_s >= dashboard_at_t_s:
            export_dashboard(now_t_s)
            exported = True

    if writer:
        close_store(writer)
    for robot_id, snapshot in snapshots.items():
        validate(snapshot, "health_snapshot")
        (paths.state_dir(folder) / f"health_{robot_id}.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    events.append("RUN_FINISHED", now_t_s, None, f"Open-loop run {run_id} finished",
                  {"anomalies_raised": len(anomalies), "predictions_issued": len(predictions)})
    score = score_run(folder, cfg["detector"])
    if not exported:
        export_dashboard(now_t_s)
    return {"folder": folder, "dashboard": dashboard, "scenario": scenario, "anomalies": anomalies,
            "cleared": cleared, "predictions": predictions, "snapshots": snapshots, "score": score}


def prediction_summary(prediction: dict, cfg: dict) -> str:
    """One plain line for the event log and the operator's alert feed."""
    ttf = prediction["predicted_ttf_s"]
    when = "no time-to-failure yet" if ttf is None else f"about {ttf / 60:.0f} min to failure"
    if prediction["fault_mode"] == "unknown":
        what = f"something is wrong with the {component_name(prediction['component'], cfg['channels'])}; cause not clear yet"
    else:
        fault = configs.get_fault(cfg["faults"], prediction["fault_mode"])["label"].lower()
        what = f"{fault} suspected ({component_name(prediction['component'], cfg['channels'])})"
    return f"{prediction['robot_id']}: {what}, {when}"


def hms(t_s: float) -> str:
    sign = "-" if t_s < 0 else ""
    t_s = abs(int(t_s))
    return f"{sign}{t_s // 3600}:{t_s % 3600 // 60:02d}:{t_s % 60:02d}"


def summarize(result: dict) -> None:
    detector_cfg = configs.load_detector_params()
    anomalies, predictions = result["anomalies"], result["predictions"]
    print(f"Anomalies raised: {len(anomalies)}   cleared: {len(result['cleared'])}   predictions issued: {len(predictions)}")
    timeline = [(e["t_s"], f"ALERT    {e['severity']:8} {e['robot_id']}  {e['message']}") for e in anomalies]
    cfg = {"channels": configs.load_channels(), "faults": configs.load_faults()}
    for p in predictions:
        flag = "WARNING!" if is_predictive_warning(p, detector_cfg) else "        "
        timeline.append((p["made_at_t_s"], f"PREDICT  {flag} {prediction_summary(p, cfg)}"))
    for t_s, line in sorted(timeline):
        print(f"  T+{hms(t_s)}  {line}")
    print("Final health:")
    for robot_id, snapshot in sorted(result["snapshots"].items()):
        flagged = [s["subsystem"] for s in snapshot["subsystems"] if s["status"] != "NORMAL"]
        print(f"  {robot_id}  {snapshot['status']:8} score {snapshot['health_score']}  {', '.join(flagged)}")
    score = result["score"]
    print(f"Score: {score['summary']}")
    for fault in score["faults"]:
        if fault["warning_lead_time_s"] is None:
            print(f"  {fault['fault_id']} {fault['fault_type']} on {fault['robot_id']}: MISSED "
                  f"(first warning named {fault['first_warning_fault_mode']})")
            continue
        print(f"  {fault['fault_id']} {fault['fault_type']} on {fault['robot_id']}: predictive warning at "
              f"T+{hms(fault['first_warning_t_s'])}, {fault['warning_lead_time_s'] / 60:.1f} min before the true failure "
              f"(target {score['target_lead_time_s'] / 60:.0f} min); diagnosis correct: {fault['diagnosis_correct']}; "
              f"predicted failure {fault['failure_time_error_s'] / 60:+.1f} min off")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generator + Missions 1-4 + scoring, open loop.")
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--dashboard-out", type=Path, default=None,
                        help="write the dashboard feeds here instead of runs/<id>__open_loop/dashboard")
    parser.add_argument("--dashboard-at", type=int, default=None, metavar="T_S",
                        help="show the fleet as it was at this time (seconds) instead of at the end")
    args = parser.parse_args()
    started = time.time()
    result = run(args.scenario, dashboard_folder=args.dashboard_out, dashboard_at_t_s=args.dashboard_at)
    print(f"Ran {result['folder']} in {time.time() - started:.1f} s")
    summarize(result)
    feed = (result["dashboard"] / "feed_index.json").resolve().relative_to(paths.REPO_ROOT)
    print(f"\nDashboard: run `make dashboard`, then open http://localhost:8000/dashboard/?feed=../{feed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
