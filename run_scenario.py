#!/usr/bin/env python3
"""Run one scenario end to end - the one command for the demo.

    python run_scenario.py scenarios/bearing_wear_p2_02.json

Writes everything to runs/<scenario_id>__seed<seed>/ and prints how to open the
dashboard on the result. While stages are still stubs, it stops at the first
unimplemented one and says which; that line is the team's progress meter.
"""

import argparse
import sys
from pathlib import Path

from p4maint import pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a P4 predictive-maintenance scenario end to end.")
    parser.add_argument("scenario", type=Path, help="path to a scenario file, e.g. scenarios/healthy_baseline.json")
    args = parser.parse_args()

    if not args.scenario.exists():
        print(f"No such scenario file: {args.scenario}")
        return 1

    try:
        folder = pipeline.run(args.scenario)
    except NotImplementedError as err:
        print(f"\nStopped: '{err}' is not implemented yet.")
        print("That is the next stage to build (see README.md 'Not yet implemented').")
        return 2

    print(f"\nRun complete: {folder}")
    print("View it:  make dashboard   then open")
    print(f"  http://localhost:8000/dashboard/?feed=../runs/{folder.name}/dashboard/feed_index.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
