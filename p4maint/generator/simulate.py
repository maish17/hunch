"""FleetSimulator: steps every robot in a scenario forward one 60 s batch at a time.

Responsibility: own the simulated world (each robot's temperatures, SOC, terrain
noise and fault progress) and produce telemetry rows. It is CLOSED LOOP: each
step reads the current fleet state, so when the fleet manager sends a robot to
P5 or puts a standby into service, that robot's operating mode changes in the
next batch. It never decides anything itself.

Mode for each robot each second (from config/state_machine.json "sim_mode"):
    MISSION          -> the mission's mode_cycle at the mission clock (t_s mod cycle length)
    MISSION_OR_IDLE  -> mission cycle if the open work order is WARNING, IDLE if CRITICAL
    anything else    -> that fixed mode (IDLE or TRAVERSE_EMPTY)

STATUS: stubs.
"""

import pandas as pd


class FleetSimulator:
    """The simulated fleet. One instance per run."""

    def __init__(self, scenario: dict, gen_params: dict, modes_cfg: dict, faults_cfg: dict,
                 channels_cfg: dict, state_machine_cfg: dict) -> None:
        """Store the configs and set every robot's starting state.

        TODO(generator owner):
          - self.t_s = 0
          - per robot: drive temps = sink temp, SOC = initial_soc_pct, terrain = 0.0,
            its faults from scenario["faults"], its random Generator (noise.make_robot_rngs)
        """
        raise NotImplementedError("FleetSimulator.__init__")

    def mode_for(self, robot_id: str, status: str, mission_id: str | None,
                 work_order_severity: str | None, t_s: int) -> str:
        """Operating mode for one robot at one second (rules in the module docstring)."""
        raise NotImplementedError("FleetSimulator.mode_for")

    def step(self, fleet_state: dict, work_order_severity: dict[str, str]) -> pd.DataFrame:
        """Advance every robot by one batch (generator.json timing.batch_s) at 1 Hz.

        fleet_state: the current fleet_state contract (status and mission per robot).
        work_order_severity: {robot_id: "WARNING"|"CRITICAL"} for robots with an open order.

        Returns one row per robot per second. Columns, in this order: robot_id, t_s,
        timestamp, op_mode, then every channel in config/channels.json order.

        TODO(generator owner): for each second and each robot -
          1. mode_for(...) -> generator_inputs from config/modes.json
          2. faults.active_fault_parameters(...)
          3. physics E1-E10 for each wheel, the lift and the battery
          4. noise.add_sensor_noise(...)
        """
        raise NotImplementedError("FleetSimulator.step")

    def repair(self, robot_id: str) -> None:
        """Remove every injected fault from this robot (P5 has fixed it).

        Called by the pipeline when the robot's work order reaches COMPLETED.
        """
        raise NotImplementedError("FleetSimulator.repair")

    def finished(self) -> bool:
        """True once t_s has reached scenario["duration_s"]."""
        raise NotImplementedError("FleetSimulator.finished")
