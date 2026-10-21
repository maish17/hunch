"""Run only the generator for a scenario:  python -m p4maint.generator scenarios/x.json

Writes runs/<run_id>__open_loop/telemetry.parquet and .../answer_key/ground_truth.json,
then prints a short summary. This is OPEN LOOP: every robot keeps its starting status
and mission for the whole run, because the fleet manager is not built yet. The full
closed-loop run is run_scenario.py; the different folder name keeps the two from
overwriting each other.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

from p4maint import configs, paths
from p4maint.generator.faults import primary_channel
from p4maint.generator.ground_truth import build_ground_truth, write_ground_truth
from p4maint.generator.scenario import check_scenario_references, load_scenario, make_run_id
from p4maint.generator.simulate import FleetSimulator, open_loop_fleet_state
from p4maint.ingest.store import append_batch, check_batch, close_store, open_store, read_telemetry


def generate(scenario_path: Path) -> Path:
    """Simulate a whole scenario open loop; return the run folder."""
    channels, modes, faults = configs.load_channels(), configs.load_modes(), configs.load_faults()
    scenario = load_scenario(scenario_path)
    problems = check_scenario_references(scenario, channels, faults)
    if problems:
        raise ValueError("Scenario problems:\n  " + "\n  ".join(problems))

    run_id = make_run_id(scenario)
    folder = paths.run_dir(run_id + "__open_loop")
    if folder.exists():
        assert paths.RUNS_DIR in folder.parents, "refusing to delete outside runs/"
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    write_ground_truth(build_ground_truth(scenario, faults, run_id), folder)
    sim = FleetSimulator(scenario, configs.load_generator_params(), modes, faults, channels,
                         configs.load_state_machine())
    fleet_state = open_loop_fleet_state(scenario)
    writer = open_store(paths.telemetry_path(folder), channels)
    while not sim.finished():
        batch = sim.step(fleet_state, {})
        batch_problems = check_batch(batch, channels, modes)
        if batch_problems:
            raise ValueError("Bad batch: " + "; ".join(batch_problems))
        append_batch(writer, batch, channels)
    close_store(writer)
    return folder


def summarize(folder: Path, scenario_path: Path) -> None:
    """Print rows, file size and, for each injected fault, how its primary channel moved."""
    scenario = load_scenario(scenario_path)
    faults = configs.load_faults()
    df = read_telemetry(paths.telemetry_path(folder))
    size_mb = paths.telemetry_path(folder).stat().st_size / 1e6
    print(f"{len(df):,} rows, {df['robot_id'].nunique()} robots, {scenario['duration_s'] / 3600:.1f} h, "
          f"telemetry.parquet {size_mb:.1f} MB")
    for fault in scenario["faults"]:
        channel = primary_channel(configs.get_fault(faults, fault["fault_type"]), fault["component"])
        rows = df[df["robot_id"] == fault["robot_id"]].set_index("t_s")
        inject, fail = fault["inject_at_s"], fault["inject_at_s"] + fault["time_to_failure_s"]
        last = min(fail, scenario["duration_s"] - 1)
        print(f"{fault['fault_id']} {fault['fault_type']} on {fault['robot_id']} {fault['component']}: "
              f"{channel} {rows.loc[inject, channel]:.2f} at injection (t={inject}) -> "
              f"{rows.loc[last, channel]:.2f} at t={last} (true failure t={fail})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate telemetry for one scenario (open loop).")
    parser.add_argument("scenario", type=Path)
    args = parser.parse_args()
    started = time.time()
    folder = generate(args.scenario)
    print(f"Generated {folder} in {time.time() - started:.1f} s")
    summarize(folder, args.scenario)
    return 0


if __name__ == "__main__":
    sys.exit(main())
