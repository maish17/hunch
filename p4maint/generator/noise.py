"""Seeded randomness: terrain process noise and sensor noise (E11, E12).

Responsibility: all randomness in a run comes from here, derived from the
scenario seed, so the same scenario + seed reproduces identical telemetry.

Rule: one numpy Generator per robot, built from the scenario seed AND the robot's
id (via a fixed checksum of the id). Each robot's random stream therefore depends
only on (seed, robot_id): adding, removing or renaming another robot never changes
it. Never use the global numpy random state or Python's random module anywhere.
"""

import math
import zlib

import numpy as np


def make_robot_rngs(seed: int, robot_ids: list[str]) -> dict[str, np.random.Generator]:
    """One independent random Generator per robot, keyed by robot_id."""
    rngs = {}
    for robot_id in sorted(robot_ids):
        robot_key = zlib.crc32(robot_id.encode("utf-8"))
        rngs[robot_id] = np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(robot_key,)))
    return rngs


def terrain_step_nm(previous_nm, gen: dict, dt_s: float, rng: np.random.Generator):
    """E11. Next terrain torque disturbance (first-order autoregressive):

    phi = exp(-dt / tau_corr)
    x_next = phi * x + sigma * sqrt(1 - phi^2) * N(0, 1)

    sigma and tau_corr: gen["terrain"]. previous_nm may be one number or a numpy array
    (one value per wheel); the result has the same shape.
    """
    terrain = gen["terrain"]
    phi = math.exp(-dt_s / terrain["correlation_time_s"])
    shock = rng.standard_normal(np.shape(previous_nm))
    return phi * np.asarray(previous_nm) + terrain["torque_sigma_nm"] * math.sqrt(1 - phi ** 2) * shock


def noise_family(channel_name: str) -> str:
    """Key in gen["sensor_noise_sigma"] for a channel: wheel_fl_current_a -> wheel_current_a."""
    parts = channel_name.split("_")
    if parts[0] == "wheel" and len(parts) >= 4:
        return "wheel_" + "_".join(parts[2:])
    return channel_name


def add_sensor_noise(true_values: dict[str, float], gen: dict, rng: np.random.Generator) -> dict[str, float]:
    """E12. Measured = true + N(0, sigma), then quantize where gen["quantization"] says.

    true_values is keyed by channel name, in channel order. One random draw per channel,
    always in that order, so results are reproducible.
    """
    sigmas = gen["sensor_noise_sigma"]
    steps = gen["quantization"]
    names = list(true_values)
    draws = rng.standard_normal(len(names))
    measured = {}
    for name, draw in zip(names, draws):
        value = true_values[name] + sigmas[noise_family(name)] * draw
        step = steps.get(name)
        if step:
            value = round(value / step) * step
        measured[name] = value
    return measured
