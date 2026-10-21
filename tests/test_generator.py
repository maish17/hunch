"""Telemetry generator: obeys docs/DECISIONS.md section 4, is reproducible, and writes
a correct answer key."""

import json
import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from p4maint import configs
from p4maint.generator import physics
from p4maint.generator.faults import active_fault_parameters, fault_progress, primary_channel
from p4maint.generator.ground_truth import answer_key_path, build_ground_truth, write_ground_truth
from p4maint.generator.scenario import check_scenario_references, load_scenario, make_run_id
from p4maint.generator.simulate import FleetSimulator, open_loop_fleet_state
from p4maint.paths import SCENARIOS_DIR
from schemas.validate import validate

GEN = configs.load_generator_params()
MODES = {m["id"]: m for m in configs.load_modes()["modes"]}
FAULTS = configs.load_faults()
CHANNELS = configs.load_channels()
EMPTY = MODES["TRAVERSE_EMPTY"]["generator_inputs"]
STEADY_STATE_ARG = {"bearing_friction_extra_nm": "bearing_extra_nm", "drag_torque_extra_nm": "drag_extra_nm",
                    "r_th_multiplier": "r_th_multiplier", "r_int_multiplier": "r_int_multiplier"}


def at_failure(fault_id: str, mode_inputs: dict = EMPTY) -> dict:
    """Noise-free steady state with the given fault at p = 1."""
    effect = configs.get_fault(FAULTS, fault_id)["generator_effect"]
    return physics.steady_state(mode_inputs, GEN, **{STEADY_STATE_ARG[effect["parameter"]]: effect["at_failure"]})


def run(scenario: dict) -> pd.DataFrame:
    sim = FleetSimulator(scenario, GEN, configs.load_modes(), FAULTS, CHANNELS, configs.load_state_machine())
    fleet = open_loop_fleet_state(scenario)
    batches = []
    while not sim.finished():
        batches.append(sim.step(fleet, {}))
    return pd.concat(batches, ignore_index=True)


def short_scenario(duration_s: int = 600, seed: int | None = None) -> dict:
    scenario = load_scenario(SCENARIOS_DIR / "healthy_baseline.json")
    scenario["duration_s"] = duration_s
    if seed is not None:
        scenario["seed"] = seed
    return scenario


class TestPhysics(unittest.TestCase):
    def test_current_proportional_to_load_torque(self):
        """E2: doubling load torque doubles motor current (I = tau / K_t)."""
        self.assertAlmostEqual(physics.motor_current_a(12.0, GEN), 2 * physics.motor_current_a(6.0, GEN))

    def test_speed_drops_as_current_rises(self):
        """E3: at fixed drive voltage, +1 A of current lowers speed by R_arm / K_e rad/s."""
        motor = GEN["drive_motor"]
        drop = physics.wheel_speed_rads(5.0, 3.0, GEN) - physics.wheel_speed_rads(5.0, 4.0, GEN)
        self.assertAlmostEqual(drop, motor["r_arm_ohm"] / motor["k_e_v_s_per_rad"])
        self.assertEqual(physics.wheel_speed_rads(0.0, 3.0, GEN), 0.0)

    def test_temperature_relaxes_to_sink(self):
        """E5: with no heat, the excess over sink falls to about 37% (1/e) after R_th * C_th seconds."""
        thermal, sink = GEN["drive_thermal"], GEN["environment"]["sink_temp_c"]
        tau = thermal["r_th_k_per_w"] * thermal["c_th_j_per_k"]
        temp = sink + 40.0
        for _ in range(int(tau)):
            temp = physics.thermal_step_c(temp, 0.0, thermal["r_th_k_per_w"], thermal["c_th_j_per_k"], sink, 1.0)
        self.assertAlmostEqual((temp - sink) / 40.0, math.exp(-1), delta=0.005)

    def test_drag_heat_does_not_enter_hub(self):
        """E4: the same extra torque heats the hub more as bearing friction than as drag,
        by exactly extra_torque * speed (drag only adds copper loss)."""
        bearing = physics.steady_state(EMPTY, GEN, bearing_extra_nm=2.0)
        drag = physics.steady_state(EMPTY, GEN, drag_extra_nm=2.0)
        self.assertAlmostEqual(bearing["current_a"], drag["current_a"])
        self.assertAlmostEqual(bearing["heat_w"] - drag["heat_w"], 2.0 * drag["speed_rads"])

    def test_voltage_sag_is_current_times_resistance(self):
        """E7/E8: V_oc - V_term == I * R_int, and V_term * I equals the bus power."""
        v_oc, r_int, power = 48.0, 0.3, 180.0
        current = physics.battery_current_a(power, v_oc, r_int)
        v_term = physics.terminal_voltage_v(v_oc, current, r_int)
        self.assertAlmostEqual(v_oc - v_term, current * r_int)
        self.assertAlmostEqual(v_term * current, power, places=6)
        with self.assertRaises(ValueError):
            physics.battery_current_a(1e6, v_oc, r_int)

    def test_ocv_interpolation_and_clamping(self):
        table = GEN["battery"]["ocv_table_soc_pct_to_v"]
        self.assertAlmostEqual(physics.ocv_from_soc_v(50, table), (47.6 + 48.8) / 2)
        self.assertEqual(physics.ocv_from_soc_v(-5, table), table[0][1])
        self.assertEqual(physics.ocv_from_soc_v(120, table), table[-1][1])

    def test_baselines_in_modes_json_match_physics(self):
        """Healthy steady state in each mode is within 5% (or 0.05 absolute near zero) of
        config/modes.json. If this fails after changing generator.json, re-derive modes.json."""
        checks = [("current_a", "wheel_fl_current_a"), ("speed_rads", "wheel_fl_speed_rads"),
                  ("temp_c", "wheel_fl_temp_c"), ("battery_current_a", "battery_current_a")]
        for mode_id, mode in MODES.items():
            state = physics.steady_state(mode["generator_inputs"], GEN)
            for key, channel in checks:
                with self.subTest(mode=mode_id, channel=channel):
                    expected = mode["baselines"][channel]
                    self.assertLessEqual(abs(state[key] - expected), max(0.05, 0.05 * abs(expected)))


class TestFaultSignatures(unittest.TestCase):
    """Every fault, at p = 1 in TRAVERSE_EMPTY, moves channels the way config/faults.json says."""

    def observe(self, fault_id: str) -> dict[str, str]:
        healthy, faulty = physics.steady_state(EMPTY, GEN), at_failure(fault_id)
        diag = configs.load_detector_params()["diagnosis"]
        current_warn = configs.get_channel(CHANNELS, "wheel_fl_current_a")["limits"]["warning_high"]
        speed_warn = configs.get_channel(CHANNELS, "wheel_fl_speed_rads")["limits"]["warning_low"]

        def direction(delta: float, scale: float) -> str:
            if delta > 0.25 * scale:
                return "UP"
            if delta < -0.25 * scale:
                return "DOWN"
            return "NORMAL"

        # Thermal residual: measured temperature minus what the NOMINAL model predicts
        # from the measured current and speed (no knowledge of the fault).
        nominal_heat = physics.drive_heat_w(faulty["current_a"], faulty["speed_rads"], GEN["drive_motor"]["bearing_friction_nm"], GEN)
        predicted_temp = GEN["environment"]["sink_temp_c"] + nominal_heat * GEN["drive_thermal"]["r_th_k_per_w"]
        thermal_residual = faulty["temp_c"] - predicted_temp
        voltage_residual = faulty["battery_voltage_v"] - (faulty["v_oc"] - faulty["battery_current_a"] * GEN["battery"]["r_int_ohm"])

        temp_delta = faulty["temp_c"] - healthy["temp_c"]
        if temp_delta > 1.0 and thermal_residual < diag["thermal_residual_excess_c"]:
            wheel_temp = "EXPLAINED_BY_CURRENT"
        else:
            wheel_temp = direction(temp_delta, 15.0)
        return {
            "wheel_current": direction(faulty["current_a"] - healthy["current_a"], current_warn),
            "wheel_speed": direction(faulty["speed_rads"] - healthy["speed_rads"], abs(speed_warn)),
            "wheel_temp": wheel_temp,
            "thermal_residual": "UP" if thermal_residual > diag["thermal_residual_excess_c"] else "NORMAL",
            "voltage_residual": "DOWN" if voltage_residual < diag["voltage_residual_excess_v"] else "NORMAL",
        }

    def test_each_fault_moves_channels_as_its_signature_says(self):
        for fault in FAULTS["faults"]:
            with self.subTest(fault=fault["id"]):
                self.assertEqual(self.observe(fault["id"]), fault["signature"])

    def test_primary_channel_reaches_critical_at_failure(self):
        """Calibration rule: at p = 1 the primary channel is at its CRITICAL limit in
        TRAVERSE_EMPTY at steady state (within 10%)."""
        healthy = physics.steady_state(EMPTY, GEN)
        for fault in FAULTS["faults"]:
            faulty = at_failure(fault["id"])
            channel = configs.get_channel(CHANNELS, primary_channel(fault, "wheel_fl_drive"))
            limits = channel["limits"]
            if channel["name"].endswith("_temp_c"):
                deviation, limit = faulty["temp_c"] - healthy["temp_c"], limits["critical_high"]
            elif channel["name"].endswith("_current_a"):
                deviation, limit = faulty["current_a"] - healthy["current_a"], limits["critical_high"]
            else:
                model = faulty["v_oc"] - faulty["battery_current_a"] * GEN["battery"]["r_int_ohm"]
                deviation, limit = faulty["battery_voltage_v"] - model, limits["critical_low"]
            with self.subTest(fault=fault["id"], channel=channel["name"]):
                self.assertAlmostEqual(deviation / limit, 1.0, delta=0.10)

    def test_progress_curve(self):
        """E13: p = 0 before injection, 0.25 halfway with exponent 2, 1 at and after failure."""
        self.assertEqual(fault_progress(100, 3600, 9000, 2.0), 0.0)
        self.assertAlmostEqual(fault_progress(3600 + 4500, 3600, 9000, 2.0), 0.25)
        self.assertEqual(fault_progress(12600, 3600, 9000, 2.0), 1.0)
        self.assertEqual(fault_progress(20000, 3600, 9000, 2.0), 1.0)

    def test_active_parameters_use_the_scenario_progression(self):
        scenario = load_scenario(SCENARIOS_DIR / "bearing_wear_p2_02.json")
        params = active_fault_parameters(scenario["faults"], FAULTS, 3600 + 4500)
        self.assertAlmostEqual(params["wheel_fl_drive"]["bearing_friction_extra_nm"], 0.25 * 2.2)
        self.assertEqual(active_fault_parameters(scenario["faults"], FAULTS, 0)["wheel_fl_drive"]["bearing_friction_extra_nm"], 0.0)


class TestSimulator(unittest.TestCase):
    def test_batch_shape_and_columns(self):
        df = run(short_scenario(120))
        expected = ["robot_id", "t_s", "timestamp", "op_mode"] + configs.channel_names(CHANNELS)
        self.assertEqual(list(df.columns), expected)
        self.assertEqual(len(df), 5 * 120)
        self.assertEqual(sorted(df["t_s"].unique().tolist()), list(range(120)))

    def test_modes_follow_status(self):
        scenario = short_scenario()
        sim = FleetSimulator(scenario, GEN, configs.load_modes(), FAULTS, CHANNELS, configs.load_state_machine())
        self.assertEqual(sim.mode_for("P2-04", "STANDBY", None, None, 0), "IDLE")
        self.assertEqual(sim.mode_for("P2-01", "ACTIVE", "M-HAUL-A", None, 0), "CARGO_HANDLING")
        self.assertEqual(sim.mode_for("P2-01", "ACTIVE", "M-HAUL-A", None, 300), "TRAVERSE_LOADED")
        self.assertEqual(sim.mode_for("P2-02", "EN_ROUTE_P5", None, "CRITICAL", 0), "TRAVERSE_EMPTY")
        self.assertEqual(sim.mode_for("P2-02", "MAINTENANCE_REQUIRED", "M-HAUL-B", "CRITICAL", 300), "IDLE")
        self.assertEqual(sim.mode_for("P2-02", "MAINTENANCE_REQUIRED", "M-HAUL-B", "WARNING", 300), "TRAVERSE_LOADED")

    def test_injected_bearing_fault_shows_in_the_data(self):
        """Fast-forwarded bearing wear on P2-02 front-left: by failure the front-left drive is
        much hotter than front-right, and its current is higher."""
        scenario = short_scenario(2400)
        scenario["robots"] = [r for r in scenario["robots"] if r["robot_id"] == "P2-02"]
        scenario["missions"] = [{"mission_id": "M-HAUL-B", "label": "flat out",
                                 "mode_cycle": [{"mode": "TRAVERSE_EMPTY", "duration_s": 60}]}]
        scenario["faults"] = [{"fault_id": "F1", "robot_id": "P2-02", "fault_type": "bearing_wear",
                               "component": "wheel_fl_drive", "inject_at_s": 0, "time_to_failure_s": 600,
                               "progression": {"shape": "power", "exponent": 1.0}}]
        end = run(scenario).tail(60)
        self.assertGreater(end["wheel_fl_temp_c"].mean() - end["wheel_fr_temp_c"].mean(), 20)
        self.assertGreater(end["wheel_fl_current_a"].mean() - end["wheel_fr_current_a"].mean(), 0.8)

    def test_repair_clears_faults(self):
        scenario = load_scenario(SCENARIOS_DIR / "bearing_wear_p2_02.json")
        sim = FleetSimulator(scenario, GEN, configs.load_modes(), FAULTS, CHANNELS, configs.load_state_machine())
        sim.repair("P2-02")
        self.assertEqual(sim.robots["P2-02"]["faults"], [])


class TestReproducibility(unittest.TestCase):
    def test_same_seed_same_telemetry(self):
        pd.testing.assert_frame_equal(run(short_scenario()), run(short_scenario()))

    def test_different_seed_different_noise(self):
        a, b = run(short_scenario(seed=1)), run(short_scenario(seed=2))
        self.assertFalse(a["wheel_fl_current_a"].equals(b["wheel_fl_current_a"]))
        self.assertAlmostEqual(a["wheel_fl_current_a"].mean(), b["wheel_fl_current_a"].mean(), delta=0.1)

    def test_adding_a_robot_does_not_change_the_others(self):
        """Per-robot random streams: P2-01's data is unchanged when a P2-00 standby is added."""
        base = short_scenario()
        bigger = short_scenario()
        bigger["robots"] = [dict(base["robots"][3], robot_id="P2-00")] + bigger["robots"]
        a = run(base).query("robot_id == 'P2-01'").reset_index(drop=True)
        b = run(bigger).query("robot_id == 'P2-01'").reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)


class TestAnswerKey(unittest.TestCase):
    def test_answer_key_written_separately_and_valid(self):
        """runs/<id>/answer_key/ground_truth.json exists, validates, and failure_t_s =
        inject_at_s + time_to_failure_s (12600 for bearing_wear_p2_02)."""
        scenario = load_scenario(SCENARIOS_DIR / "bearing_wear_p2_02.json")
        truth = build_ground_truth(scenario, FAULTS, make_run_id(scenario))
        with tempfile.TemporaryDirectory() as tmp:
            path = write_ground_truth(truth, Path(tmp))
            self.assertEqual(path, answer_key_path(Path(tmp)))
            self.assertEqual(path.parent.name, "answer_key")
            written = json.loads(path.read_text())
        validate(written, "ground_truth")
        fault = written["faults"][0]
        self.assertEqual(fault["failure_t_s"], 12600)
        self.assertEqual(fault["failure_at"], "2027-03-01T03:30:00Z")
        self.assertEqual(fault["primary_channel"], "wheel_fl_temp_c")

    def test_healthy_scenario_has_empty_answer_key(self):
        scenario = load_scenario(SCENARIOS_DIR / "healthy_baseline.json")
        self.assertEqual(build_ground_truth(scenario, FAULTS, "x")["faults"], [])

    def test_scenario_reference_checks(self):
        scenario = load_scenario(SCENARIOS_DIR / "bearing_wear_p2_02.json")
        self.assertEqual(check_scenario_references(scenario, CHANNELS, FAULTS), [])
        scenario["faults"][0]["component"] = "battery_pack"
        scenario["robots"][0]["mission_id"] = "M-NOWHERE"  # P2-01 is ACTIVE
        problems = check_scenario_references(scenario, CHANNELS, FAULTS)
        self.assertEqual(len(problems), 2, problems)


if __name__ == "__main__":
    unittest.main()
