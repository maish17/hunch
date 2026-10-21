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

Every number comes from config/generator.json and config/modes.json; the
equations are in physics.py.
"""

import numpy as np
import pandas as pd

from p4maint.configs import channel_names, get_mode
from p4maint.generator import physics
from p4maint.generator.faults import active_fault_parameters
from p4maint.generator.noise import add_sensor_noise, make_robot_rngs, terrain_step_nm

WHEELS = ["fl", "fr", "rl", "rr"]


class FleetSimulator:
    """The simulated fleet. One instance per run."""

    def __init__(self, scenario: dict, gen_params: dict, modes_cfg: dict, faults_cfg: dict,
                 channels_cfg: dict, state_machine_cfg: dict) -> None:
        """Store the configs and set every robot's starting state."""
        self.scenario = scenario
        self.gen = gen_params
        self.modes_cfg = modes_cfg
        self.faults_cfg = faults_cfg
        self.state_machine_cfg = state_machine_cfg
        self.channels = channel_names(channels_cfg)
        self.batch_s = gen_params["timing"]["batch_s"]
        self.dt_s = gen_params["timing"]["integration_dt_s"]
        self.start = pd.Timestamp(scenario["start_time_utc"])
        self.t_s = 0

        self.missions = {}
        for mission in scenario["missions"]:
            self.missions[mission["mission_id"]] = mission["mode_cycle"]

        robot_ids = [robot["robot_id"] for robot in scenario["robots"]]
        rngs = make_robot_rngs(scenario["seed"], robot_ids)
        sink = gen_params["environment"]["sink_temp_c"]
        self.robots = {}
        for robot in scenario["robots"]:
            robot_id = robot["robot_id"]
            self.robots[robot_id] = {
                "temps_c": {wheel: sink for wheel in WHEELS},
                "terrain_nm": np.zeros(len(WHEELS)),
                "soc_pct": robot["initial_soc_pct"],
                "faults": [f for f in scenario["faults"] if f["robot_id"] == robot_id],
                "rng": rngs[robot_id],
            }

    def mission_mode(self, mission_id: str, t_s: int) -> str:
        """Where the mission's repeating mode cycle is at time t_s."""
        cycle = self.missions[mission_id]
        cycle_length = sum(step["duration_s"] for step in cycle)
        position = t_s % cycle_length
        for step in cycle:
            if position < step["duration_s"]:
                return step["mode"]
            position -= step["duration_s"]
        return cycle[-1]["mode"]

    def mode_for(self, robot_id: str, status: str, mission_id: str | None,
                 work_order_severity: str | None, t_s: int) -> str:
        """Operating mode for one robot at one second (rules in the module docstring)."""
        sim_mode = self.state_machine_cfg["robot"]["states"][status]["sim_mode"]
        if sim_mode == "MISSION_OR_IDLE":
            if work_order_severity == "CRITICAL" or mission_id is None:
                return "IDLE"
            return self.mission_mode(mission_id, t_s)
        if sim_mode == "MISSION":
            if mission_id is None:
                return "IDLE"
            return self.mission_mode(mission_id, t_s)
        return sim_mode

    def _sample(self, robot_id: str, mode: str, t_s: int) -> dict[str, float]:
        """True (noise-free) channel values at t_s, then advance this robot's state by dt."""
        gen = self.gen
        state = self.robots[robot_id]
        inputs = get_mode(self.modes_cfg, mode)["generator_inputs"]
        params = active_fault_parameters(state["faults"], self.faults_cfg, t_s)
        voltage = inputs["drive_voltage_v"]
        moving = voltage > 0
        total_mass = gen["robot"]["mass_kg"] + inputs["cargo_mass_kg"]

        state["terrain_nm"] = terrain_step_nm(state["terrain_nm"], gen, self.dt_s, state["rng"])
        values = {}
        wheel_currents = []
        for index, wheel in enumerate(WHEELS):
            drive = params.get(f"wheel_{wheel}_drive", {})
            thermal = params.get(f"wheel_{wheel}_thermal", {})
            bearing_extra = drive.get("bearing_friction_extra_nm", 0.0)
            if moving:
                torque = physics.wheel_load_torque_nm(total_mass, gen, bearing_extra,
                                                      drive.get("drag_torque_extra_nm", 0.0),
                                                      float(state["terrain_nm"][index]))
                current = physics.motor_current_a(torque, gen)
                speed = physics.wheel_speed_rads(voltage, current, gen)
            else:
                current, speed = 0.0, 0.0
            wheel_currents.append(current)
            temp = state["temps_c"][wheel]
            values[f"wheel_{wheel}_current_a"] = current
            values[f"wheel_{wheel}_speed_rads"] = speed
            values[f"wheel_{wheel}_temp_c"] = temp
            heat = physics.drive_heat_w(current, speed, gen["drive_motor"]["bearing_friction_nm"] + bearing_extra, gen)
            r_th = gen["drive_thermal"]["r_th_k_per_w"] * thermal.get("r_th_multiplier", 1.0)
            state["temps_c"][wheel] = physics.thermal_step_c(temp, heat, r_th, gen["drive_thermal"]["c_th_j_per_k"],
                                                             gen["environment"]["sink_temp_c"], self.dt_s)

        battery = gen["battery"]
        r_int = battery["r_int_ohm"] * params.get("battery_pack", {}).get("r_int_multiplier", 1.0)
        v_oc = physics.ocv_from_soc_v(state["soc_pct"], battery["ocv_table_soc_pct_to_v"])
        if inputs["charger_current_a"] > 0:
            i_batt = -inputs["charger_current_a"]
        else:
            power = physics.bus_power_w(voltage, wheel_currents, inputs["lift_current_a"], gen)
            i_batt = physics.battery_current_a(power, v_oc, r_int)
        values["battery_voltage_v"] = physics.terminal_voltage_v(v_oc, i_batt, r_int)
        values["battery_current_a"] = i_batt
        values["battery_soc_pct"] = state["soc_pct"]
        values["lift_joint_current_a"] = inputs["lift_current_a"]
        values["lift_joint_pos_err_deg"] = inputs["lift_pos_err_deg"]
        state["soc_pct"] = physics.soc_step_pct(state["soc_pct"], i_batt, battery["capacity_ah"], self.dt_s)

        return {name: values[name] for name in self.channels}

    def step(self, fleet_state: dict, work_order_severity: dict[str, str]) -> pd.DataFrame:
        """Advance every robot by one batch (generator.json timing.batch_s) at 1 Hz.

        fleet_state: the current fleet_state contract (only robot_id, status and
        mission_id are read). work_order_severity: {robot_id: "WARNING"|"CRITICAL"} for
        robots with an open work order.

        Returns one row per robot per second, sorted by robot then time. Columns, in
        order: robot_id, t_s, timestamp, op_mode, then every channel in
        config/channels.json order (float32).
        """
        status_by_robot = {robot["robot_id"]: robot for robot in fleet_state["robots"]}
        rows = []
        for robot_id in sorted(self.robots):
            fleet_robot = status_by_robot[robot_id]
            for k in range(self.batch_s):
                t_s = self.t_s + k
                mode = self.mode_for(robot_id, fleet_robot["status"], fleet_robot["mission_id"],
                                     work_order_severity.get(robot_id), t_s)
                true_values = self._sample(robot_id, mode, t_s)
                measured = add_sensor_noise(true_values, self.gen, self.robots[robot_id]["rng"])
                row = {"robot_id": robot_id, "t_s": t_s, "op_mode": mode}
                row.update(measured)
                rows.append(row)
        self.t_s += self.batch_s

        df = pd.DataFrame(rows)
        df.insert(2, "timestamp", self.start + pd.to_timedelta(df["t_s"], unit="s"))
        df["t_s"] = df["t_s"].astype("int64")
        for name in self.channels:
            df[name] = df[name].astype("float32")
        return df[["robot_id", "t_s", "timestamp", "op_mode"] + self.channels]

    def repair(self, robot_id: str) -> None:
        """Remove every injected fault from this robot (P5 has fixed it).

        Called by the pipeline when the robot's work order reaches COMPLETED. The
        answer key is not changed: it records what was injected.
        """
        self.robots[robot_id]["faults"] = []

    def finished(self) -> bool:
        """True once t_s has reached scenario["duration_s"]."""
        return self.t_s >= self.scenario["duration_s"]


def open_loop_fleet_state(scenario: dict) -> dict:
    """A fleet state where every robot keeps its starting status and mission forever.

    Used by `python -m p4maint.generator` and the tests, which run the simulator on
    its own before the fleet manager exists. Only the fields the simulator reads.
    """
    robots = []
    for robot in scenario["robots"]:
        robots.append({"robot_id": robot["robot_id"], "status": robot["initial_status"],
                       "mission_id": robot["mission_id"]})
    return {"robots": robots}
