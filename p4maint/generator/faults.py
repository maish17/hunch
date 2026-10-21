"""Fault injection: how far along each fault is, and what it changes (E13).

Responsibility: given the scenario's fault list and the time, say which physical
parameter of which component is perturbed and by how much. Does not know anything
about detection. Definitions come from config/faults.json.
"""

from p4maint.configs import get_fault


def fault_progress(t_s: float, inject_at_s: float, time_to_failure_s: float, exponent: float) -> float:
    """E13. Progress p in [0, 1]:

    p = 0                                                    before injection
    p = ((t - inject_at_s) / time_to_failure_s) ** exponent  while developing
    p = 1                                                    at and after true failure
    """
    if t_s <= inject_at_s:
        return 0.0
    fraction = (t_s - inject_at_s) / time_to_failure_s
    if fraction >= 1.0:
        return 1.0
    return fraction ** exponent


def parameter_value(fault_def: dict, p: float) -> float:
    """Perturbed parameter value: healthy_value + p * (at_failure - healthy_value).

    fault_def is one entry of config/faults.json "faults"; uses its generator_effect.
    """
    effect = fault_def["generator_effect"]
    return effect["healthy_value"] + p * (effect["at_failure"] - effect["healthy_value"])


def active_fault_parameters(robot_faults: list[dict], faults_cfg: dict, t_s: float) -> dict[str, dict[str, float]]:
    """Every perturbed parameter for one robot at time t_s, keyed by component.

    Example return value:
        {"wheel_fl_drive": {"bearing_friction_extra_nm": 0.81},
         "battery_pack": {"r_int_multiplier": 1.4}}

    robot_faults are this robot's entries from scenario["faults"]. The scenario's
    progression is used if given, else the fault's default_progression. Components
    with no fault are absent (the simulator uses healthy values). If two faults hit
    the same parameter, extra torques add and multipliers multiply.
    """
    params: dict[str, dict[str, float]] = {}
    for fault in robot_faults:
        fault_def = get_fault(faults_cfg, fault["fault_type"])
        progression = fault.get("progression", fault_def["default_progression"])
        p = fault_progress(t_s, fault["inject_at_s"], fault["time_to_failure_s"], progression["exponent"])
        name = fault_def["generator_effect"]["parameter"]
        value = parameter_value(fault_def, p)
        component_params = params.setdefault(fault["component"], {})
        if name not in component_params:
            component_params[name] = value
        elif name.endswith("_multiplier"):
            component_params[name] *= value
        else:
            component_params[name] += value
    return params


def primary_channel(fault_def: dict, component: str) -> str:
    """Name of the channel that defines failure for this fault on this component.

    e.g. bearing_wear on wheel_fl_drive -> "wheel_fl_temp_c". The wheel is the second
    part of the component name (wheel_fl_drive, wheel_fl_thermal).
    """
    pattern = fault_def["primary_channel_pattern"]
    if "{wheel}" not in pattern:
        return pattern
    wheel = component.split("_")[1]
    return pattern.replace("{wheel}", wheel)
