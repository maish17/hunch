"""Seeded randomness: terrain process noise and sensor noise (E11, E12).

Responsibility: all randomness in a run comes from here, derived from the
scenario seed, so the same scenario + seed reproduces identical telemetry.

Rule: one numpy Generator per robot, created with
np.random.SeedSequence(seed).spawn(n_robots) in sorted robot_id order. Never use
the global numpy random state or Python's random module anywhere in the project.

STATUS: stubs.
"""

import numpy as np


def make_robot_rngs(seed: int, robot_ids: list[str]) -> dict[str, np.random.Generator]:
    """One independent random Generator per robot, keyed by robot_id (sorted order)."""
    raise NotImplementedError("make_robot_rngs")


def terrain_step_nm(previous_nm: float, gen: dict, dt_s: float, rng: np.random.Generator) -> float:
    """E11. Next terrain torque disturbance for one wheel (first-order autoregressive):

    phi = exp(-dt / tau_corr)
    x_next = phi * x + sigma * sqrt(1 - phi^2) * N(0, 1)

    sigma and tau_corr: gen["terrain"]. Only applied while the wheel is moving.
    """
    raise NotImplementedError("E11 terrain_step_nm")


def add_sensor_noise(true_values: dict[str, float], gen: dict, rng: np.random.Generator) -> dict[str, float]:
    """E12. Measured = true + N(0, sigma), then quantize where gen["quantization"] says.

    true_values is keyed by channel name. sigma comes from gen["sensor_noise_sigma"],
    whose keys are channel families (wheel_current_a covers wheel_fl_current_a, etc.).
    """
    raise NotImplementedError("E12 add_sensor_noise")
