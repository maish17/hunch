"""Telemetry generator. STUBS: remove @skip as p4maint/generator is built.

These check the generator obeys docs/DECISIONS.md section 4, is reproducible,
and writes a correct answer key.
"""

import unittest

TODO = unittest.skip("TODO(generator): needs p4maint.generator")


class TestPhysics(unittest.TestCase):
    @TODO
    def test_current_proportional_to_load_torque(self):
        """E2: doubling load torque doubles motor current (I = tau / K_t)."""

    @TODO
    def test_speed_drops_as_current_rises(self):
        """E3: at fixed drive voltage, +1 A of current lowers speed by R_arm / K_e rad/s."""

    @TODO
    def test_temperature_relaxes_to_sink(self):
        """E5: with no heat, temperature falls to 37% of its excess over sink after R_th * C_th s."""

    @TODO
    def test_drag_heat_does_not_enter_hub(self):
        """E4: drag torque raises current (copper loss) but adds no friction heat."""

    @TODO
    def test_voltage_sag_is_current_times_resistance(self):
        """E7/E8: V_oc - V_term == I * R_int, and the bus power balance holds."""

    @TODO
    def test_baselines_in_modes_json_match_physics(self):
        """Healthy steady state in each mode is within 5% of config/modes.json baselines."""


class TestFaultSignatures(unittest.TestCase):
    @TODO
    def test_each_fault_moves_channels_as_its_signature_says(self):
        """For each fault at p = 1 in TRAVERSE_EMPTY, every signature element in
        config/faults.json has the stated direction (UP / DOWN / NORMAL / EXPLAINED_BY_CURRENT)."""

    @TODO
    def test_primary_channel_reaches_critical_at_failure(self):
        """Calibration rule: at p = 1 the primary channel is at its CRITICAL limit in
        TRAVERSE_EMPTY at steady state (within 10%)."""

    @TODO
    def test_progress_curve(self):
        """E13: p = 0 before injection, 0.25 halfway with exponent 2, 1 at and after failure."""


class TestReproducibility(unittest.TestCase):
    @TODO
    def test_same_seed_same_telemetry(self):
        """Two runs of one scenario produce identical DataFrames."""

    @TODO
    def test_different_seed_different_noise(self):
        """Changing only the seed changes the noise, not the means."""

    @TODO
    def test_adding_a_robot_does_not_change_the_others(self):
        """Per-robot random streams: robot P2-01's data is unchanged when P2-06 is added."""


class TestAnswerKey(unittest.TestCase):
    @TODO
    def test_answer_key_written_separately_and_valid(self):
        """runs/<id>/answer_key/ground_truth.json exists, validates, and failure_t_s =
        inject_at_s + time_to_failure_s (12600 for bearing_wear_p2_02)."""

    @TODO
    def test_healthy_scenario_has_empty_answer_key(self):
        """healthy_baseline writes an answer key with faults = []."""


if __name__ == "__main__":
    unittest.main()
