"""Fault injection: how far along each fault is, and what it changes (E13).

Responsibility: given the scenario's fault list and the time, say which physical
parameter of which component is perturbed and by how much. Does not know anything
about detection. Definitions come from config/faults.json.

STATUS: stubs.
"""


def fault_progress(t_s: float, inject_at_s: float, time_to_failure_s: float, exponent: float) -> float:
    """E13. Progress p in [0, 1]:

    p = 0                                                  before injection
    p = ((t - inject_at_s) / time_to_failure_s) ** exponent  while developing
    p = 1                                                  at and after true failure
    """
    raise NotImplementedError("E13 fault_progress")


def parameter_value(fault_def: dict, p: float) -> float:
    """Perturbed parameter value: healthy_value + p * (at_failure - healthy_value).

    fault_def is one entry of config/faults.json "faults"; uses its generator_effect.
    """
    raise NotImplementedError("parameter_value")


def active_fault_parameters(robot_faults: list[dict], faults_cfg: dict, t_s: float) -> dict[str, dict[str, float]]:
    """Every perturbed parameter for one robot at time t_s, keyed by component.

    Example return value:
        {"wheel_fl_drive": {"bearing_friction_extra_nm": 0.81},
         "battery_pack": {"r_int_multiplier": 1.0}}

    robot_faults are this robot's entries from scenario["faults"]. Use the scenario's
    progression if given, else the fault's default_progression. Components with no
    fault are simply absent (the simulator uses healthy values).

    TODO(generator owner): implement with fault_progress() and parameter_value().
    """
    raise NotImplementedError("active_fault_parameters")


def primary_channel(fault_def: dict, component: str) -> str:
    """Name of the channel that defines failure for this fault on this component.

    e.g. bearing_wear on wheel_fl_drive -> "wheel_fl_temp_c". Fill {wheel} in
    fault_def["primary_channel_pattern"] from the component name.
    """
    raise NotImplementedError("primary_channel")
