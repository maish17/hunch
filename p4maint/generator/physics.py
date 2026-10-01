"""The physical relationships the generator must obey (E1-E10).

Responsibility: pure functions, one per equation in docs/DECISIONS.md section 4.
They take numbers in and give numbers out - no state, no randomness, no file
access - so each one can be unit-tested by hand with a calculator.

All parameters come from config/generator.json (passed in as `gen`). Absolute
magnitudes are scaled; what must be right is how channels move together.

STATUS: stubs. Each body is a TODO with the equation it must implement.
"""


def wheel_load_torque_nm(total_mass_kg: float, gen: dict, bearing_extra_nm: float,
                         drag_extra_nm: float, terrain_nm: float) -> float:
    """E1. Load torque on ONE wheel's motor shaft, N*m.

    tau_load = C_rr * m_total * g / n_wheels * r_wheel      (rolling resistance)
             + tau_bearing0 + bearing_extra_nm              (bearing friction, bearing_wear fault)
             + drag_extra_nm                                (regolith drag, wheel_drag fault)
             + terrain_nm                                   (random terrain variation, E11)

    C_rr, g, n_wheels, r_wheel: gen["environment"], gen["robot"]; tau_bearing0: gen["drive_motor"].
    """
    raise NotImplementedError("E1 wheel_load_torque_nm")


def motor_current_a(load_torque_nm: float, gen: dict) -> float:
    """E2. Motor current, A:  I = tau_load / K_t.

    Steady state each sample: motor electrical and mechanical time constants are far
    shorter than our 1 s sample period.
    """
    raise NotImplementedError("E2 motor_current_a")


def wheel_speed_rads(drive_voltage_v: float, current_a: float, gen: dict) -> float:
    """E3. Wheel speed, rad/s:  omega = (V_drive - I * R_arm) / K_e.

    Return 0.0 when drive_voltage_v is 0 (robot parked). Never negative.
    This is why speed DROPS when current rises: more voltage is lost across R_arm.
    """
    raise NotImplementedError("E3 wheel_speed_rads")


def drive_heat_w(current_a: float, speed_rads: float, bearing_torque_nm: float, gen: dict) -> float:
    """E4. Heat delivered into the drive housing, W:

    P_heat = I^2 * R_arm  +  tau_bearing * omega
             (copper loss)   (bearing friction heat)

    bearing_torque_nm is tau_bearing0 + the bearing_wear extra. Regolith drag torque is
    NOT included: that work is done on the soil outside the hub. This single line is
    what lets bearing_wear and wheel_drag be told apart.
    """
    raise NotImplementedError("E4 drive_heat_w")


def thermal_step_c(temp_c: float, heat_w: float, r_th_k_per_w: float, c_th_j_per_k: float,
                   sink_temp_c: float, dt_s: float) -> float:
    """E5. Drive temperature after one time step, degC (explicit Euler):

    C_th * dT/dt = P_heat - (T - T_sink) / R_th
    T_next = T + dt / C_th * (P_heat - (T - T_sink) / R_th)

    With no heat, T decays toward T_sink with time constant R_th * C_th (600 s).
    The cooling_fault multiplies R_th, so the same heat gives a higher temperature.
    Stable because dt (1 s) is much smaller than R_th * C_th.
    """
    raise NotImplementedError("E5 thermal_step_c")


def bus_power_w(drive_voltage_v: float, wheel_currents_a: list[float], lift_current_a: float, gen: dict) -> float:
    """E6. Electrical power drawn from the battery, W:

    P_bus = sum(V_drive * I_wheel) / eta_driver  +  P_hotel  +  V_lift * I_lift / eta_driver
    """
    raise NotImplementedError("E6 bus_power_w")


def battery_current_a(bus_power_w_: float, v_oc: float, r_int_ohm: float) -> float:
    """E7. Battery discharge current, A (positive = discharging):

    From P_bus = V_term * I and V_term = V_oc - I * R_int:
        I = (V_oc - sqrt(V_oc^2 - 4 * R_int * P_bus)) / (2 * R_int)

    If the square root's argument goes negative the pack cannot deliver P_bus:
    raise ValueError (that is a brown-out). In CHARGING mode the simulator uses
    -charger_current_a instead of this function.
    """
    raise NotImplementedError("E7 battery_current_a")


def terminal_voltage_v(v_oc: float, battery_current: float, r_int_ohm: float) -> float:
    """E8. Battery terminal voltage, V:  V_term = V_oc(SOC) - I * R_int.

    battery_degradation multiplies R_int, so the sag I * R_int grows with load and time.
    """
    raise NotImplementedError("E8 terminal_voltage_v")


def soc_step_pct(soc_pct: float, battery_current: float, capacity_ah: float, dt_s: float) -> float:
    """E9. State of charge after one step, % (coulomb counting):

    SOC_next = SOC - I * dt / (3600 * Q_Ah) * 100, clipped to [0, 100].
    """
    raise NotImplementedError("E9 soc_step_pct")


def ocv_from_soc_v(soc_pct: float, ocv_table: list[list[float]]) -> float:
    """E10. Open-circuit voltage, V, by straight-line interpolation in
    gen["battery"]["ocv_table_soc_pct_to_v"] ([[soc, volts], ...], sorted by soc).
    """
    raise NotImplementedError("E10 ocv_from_soc_v")
