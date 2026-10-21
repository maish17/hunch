"""The physical relationships the generator must obey (E1-E10).

Responsibility: pure functions, one per equation in docs/DECISIONS.md section 4.
They take numbers in and give numbers out - no state, no randomness, no file
access - so each one can be checked by hand with a calculator.

All parameters come from config/generator.json (passed in as `gen`). Absolute
magnitudes are scaled; what must be right is how channels move together.

steady_state() at the bottom chains the equations together for one operating mode
with no noise. The tests use it to check config/modes.json baselines and the fault
calibration in config/faults.json against the physics.
"""

import math


def wheel_load_torque_nm(total_mass_kg: float, gen: dict, bearing_extra_nm: float,
                         drag_extra_nm: float, terrain_nm: float) -> float:
    """E1. Load torque on ONE wheel's motor shaft, N*m.

    tau_load = C_rr * m_total * g / n_wheels * r_wheel      (rolling resistance)
             + tau_bearing0 + bearing_extra_nm              (bearing friction, bearing_wear fault)
             + drag_extra_nm                                (regolith drag, wheel_drag fault)
             + terrain_nm                                   (random terrain variation, E11)
    """
    env, robot = gen["environment"], gen["robot"]
    rolling = env["rolling_resistance_coeff"] * total_mass_kg * env["gravity_mps2"] / robot["n_wheels"] * robot["wheel_radius_m"]
    bearing = gen["drive_motor"]["bearing_friction_nm"] + bearing_extra_nm
    return rolling + bearing + drag_extra_nm + terrain_nm


def motor_current_a(load_torque_nm: float, gen: dict) -> float:
    """E2. Motor current, A:  I = tau_load / K_t.

    Steady state each sample: motor electrical and mechanical time constants are far
    shorter than our 1 s sample period.
    """
    return load_torque_nm / gen["drive_motor"]["k_t_nm_per_a"]


def wheel_speed_rads(drive_voltage_v: float, current_a: float, gen: dict) -> float:
    """E3. Wheel speed, rad/s:  omega = (V_drive - I * R_arm) / K_e.

    0.0 when drive_voltage_v is 0 (robot parked). Never negative.
    This is why speed DROPS when current rises: more voltage is lost across R_arm.
    """
    if drive_voltage_v <= 0:
        return 0.0
    motor = gen["drive_motor"]
    speed = (drive_voltage_v - current_a * motor["r_arm_ohm"]) / motor["k_e_v_s_per_rad"]
    return max(speed, 0.0)


def drive_heat_w(current_a: float, speed_rads: float, bearing_torque_nm: float, gen: dict) -> float:
    """E4. Heat delivered into the drive housing, W:

    P_heat = I^2 * R_arm  +  tau_bearing * omega
             (copper loss)   (bearing friction heat)

    bearing_torque_nm is tau_bearing0 + the bearing_wear extra. Regolith drag torque is
    NOT included: that work is done on the soil outside the hub. This single line is
    what lets bearing_wear and wheel_drag be told apart.
    """
    copper_loss = current_a ** 2 * gen["drive_motor"]["r_arm_ohm"]
    friction_heat = bearing_torque_nm * speed_rads
    return copper_loss + friction_heat


def thermal_step_c(temp_c: float, heat_w: float, r_th_k_per_w: float, c_th_j_per_k: float,
                   sink_temp_c: float, dt_s: float) -> float:
    """E5. Drive temperature after one time step, degC (explicit Euler):

    C_th * dT/dt = P_heat - (T - T_sink) / R_th
    T_next = T + dt / C_th * (P_heat - (T - T_sink) / R_th)

    With no heat, T decays toward T_sink with time constant R_th * C_th (600 s).
    The cooling_fault multiplies R_th, so the same heat gives a higher temperature.
    Stable because dt (1 s) is much smaller than R_th * C_th.
    """
    heat_out = (temp_c - sink_temp_c) / r_th_k_per_w
    return temp_c + dt_s / c_th_j_per_k * (heat_w - heat_out)


def bus_power_w(drive_voltage_v: float, wheel_currents_a: list[float], lift_current_a: float, gen: dict) -> float:
    """E6. Electrical power drawn from the battery, W:

    P_bus = sum(V_drive * I_wheel) / eta_driver  +  P_hotel  +  V_lift * I_lift / eta_driver
    """
    eta = gen["drive_motor"]["driver_efficiency"]
    loads = gen["loads"]
    drive_power = 0.0
    for current in wheel_currents_a:
        drive_power += drive_voltage_v * current
    lift_power = loads["lift_bus_voltage_v"] * lift_current_a
    return drive_power / eta + loads["hotel_load_w"] + lift_power / eta


def battery_current_a(bus_power_w_: float, v_oc: float, r_int_ohm: float) -> float:
    """E7. Battery discharge current, A (positive = discharging):

    From P_bus = V_term * I and V_term = V_oc - I * R_int:
        I = (V_oc - sqrt(V_oc^2 - 4 * R_int * P_bus)) / (2 * R_int)

    If the square root's argument goes negative the pack cannot deliver P_bus:
    raises ValueError (that is a brown-out). In CHARGING mode the simulator uses
    -charger_current_a instead of this function.
    """
    if r_int_ohm <= 0:
        return bus_power_w_ / v_oc
    discriminant = v_oc ** 2 - 4 * r_int_ohm * bus_power_w_
    if discriminant < 0:
        raise ValueError(f"Brown-out: pack cannot deliver {bus_power_w_:.0f} W at V_oc {v_oc:.1f} V, R_int {r_int_ohm:.3f} ohm")
    return (v_oc - math.sqrt(discriminant)) / (2 * r_int_ohm)


def terminal_voltage_v(v_oc: float, battery_current: float, r_int_ohm: float) -> float:
    """E8. Battery terminal voltage, V:  V_term = V_oc(SOC) - I * R_int.

    battery_degradation multiplies R_int, so the sag I * R_int grows with load and time.
    """
    return v_oc - battery_current * r_int_ohm


def soc_step_pct(soc_pct: float, battery_current: float, capacity_ah: float, dt_s: float) -> float:
    """E9. State of charge after one step, % (coulomb counting):

    SOC_next = SOC - I * dt / (3600 * Q_Ah) * 100, clipped to [0, 100].
    """
    soc = soc_pct - battery_current * dt_s / (3600 * capacity_ah) * 100
    return min(max(soc, 0.0), 100.0)


def ocv_from_soc_v(soc_pct: float, ocv_table: list[list[float]]) -> float:
    """E10. Open-circuit voltage, V, by straight-line interpolation in
    gen["battery"]["ocv_table_soc_pct_to_v"] ([[soc, volts], ...], sorted by soc).
    Values outside the table are clamped to its ends.
    """
    if soc_pct <= ocv_table[0][0]:
        return ocv_table[0][1]
    for (soc_lo, v_lo), (soc_hi, v_hi) in zip(ocv_table, ocv_table[1:]):
        if soc_pct <= soc_hi:
            return v_lo + (v_hi - v_lo) * (soc_pct - soc_lo) / (soc_hi - soc_lo)
    return ocv_table[-1][1]


def steady_state(mode_inputs: dict, gen: dict, soc_pct: float = 50.0, bearing_extra_nm: float = 0.0,
                 drag_extra_nm: float = 0.0, r_th_multiplier: float = 1.0, r_int_multiplier: float = 1.0) -> dict:
    """Noise-free steady state of one wheel and the battery in one operating mode.

    mode_inputs is a mode's generator_inputs from config/modes.json. The fault
    arguments apply to the wheel being calculated (or the pack, for r_int_multiplier),
    so the healthy value and the faulty value can be compared directly.

    Returns current_a, speed_rads, heat_w, temp_c (thermal steady state: sink + P * R_th),
    battery_current_a (assuming all four wheels behave like this one) and battery_voltage_v.
    """
    cargo = mode_inputs["cargo_mass_kg"]
    voltage = mode_inputs["drive_voltage_v"]
    moving = voltage > 0
    if moving:
        torque = wheel_load_torque_nm(gen["robot"]["mass_kg"] + cargo, gen, bearing_extra_nm, drag_extra_nm, 0.0)
        current = motor_current_a(torque, gen)
        speed = wheel_speed_rads(voltage, current, gen)
    else:
        current, speed = 0.0, 0.0
    bearing_torque = gen["drive_motor"]["bearing_friction_nm"] + bearing_extra_nm
    heat = drive_heat_w(current, speed, bearing_torque, gen)
    r_th = gen["drive_thermal"]["r_th_k_per_w"] * r_th_multiplier
    temp = gen["environment"]["sink_temp_c"] + heat * r_th

    battery = gen["battery"]
    r_int = battery["r_int_ohm"] * r_int_multiplier
    v_oc = ocv_from_soc_v(soc_pct, battery["ocv_table_soc_pct_to_v"])
    if mode_inputs["charger_current_a"] > 0:
        i_batt = -mode_inputs["charger_current_a"]
    else:
        power = bus_power_w(voltage, [current] * gen["robot"]["n_wheels"], mode_inputs["lift_current_a"], gen)
        i_batt = battery_current_a(power, v_oc, r_int)
    return {
        "current_a": current, "speed_rads": speed, "heat_w": heat, "temp_c": temp,
        "battery_current_a": i_batt, "battery_voltage_v": terminal_voltage_v(v_oc, i_batt, r_int),
        "v_oc": v_oc,
    }
