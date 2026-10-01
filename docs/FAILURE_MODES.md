# Failure modes (PDR scope: exactly four)

Robot: P2 transport (4 hub-driven wheels, cargo-lift actuator, 13S Li-ion pack).
Machine-readable source: [`config/faults.json`](../config/faults.json). If this table and that file disagree, the file wins; fix the table.

## The table

| Fault (`id`) | What physically fails | Subsystem / component | Wheel current | Wheel speed | Drive temperature | Thermal residual¹ | Voltage residual² | Severity³ | Recommended action (code) | Est. repair⁴ |
|---|---|---|---|---|---|---|---|---|---|---|
| Hub bearing wear (`bearing_wear`) | Worn or regolith-contaminated hub bearing adds friction torque; the friction heats the hub directly | MOBILITY / `wheel_{w}_drive` | **UP** | **DOWN** | **UP** (a lot) | **UP** | normal | CRITICAL | Stop when safe, go to P5, replace hub bearing, inspect seals and gearbox (`REPLACE_HUB_BEARING`) | 3 h |
| Wheel drag in regolith (`wheel_drag`) | Regolith packed into the wheel well and tread adds rolling resistance; the extra work goes into the soil | MOBILITY / `wheel_{w}_drive` | **UP** | **DOWN** | rises only as much as current explains | normal (≈ 0) | normal | WARNING | Reduce speed and payload; at P5 clear wheel well, tread and seals (`CLEAN_WHEEL_AND_SEALS`) | 1 h |
| Thermal / cooling fault (`cooling_fault`) | Dust on the radiator or a degraded thermal strap raises thermal resistance; same heat in, worse heat out | THERMAL / `wheel_{w}_thermal` | normal | normal | **UP** | **UP** | normal | WARNING | Limit drive duty cycle; at P5 clean radiator, inspect strap / heat pipe (`CLEAN_RADIATOR_CHECK_STRAP`) | 1.5 h |
| Battery degradation (`battery_degradation`) | Pack internal resistance rises with ageing; terminal voltage sags more under load, and it worsens over time | POWER / `battery_pack` | normal | normal | normal | normal | **DOWN**, bigger at high current | WARNING | Limit peak load, keep SOC high; at P5 impedance test, replace weak module or pack (`REPLACE_BATTERY_MODULE`) | 2 h |

¹ **Thermal residual** = measured drive temperature − the temperature the detector's thermal model predicts from the *measured* current and speed. Positive means heat that the current does not explain.
² **Voltage residual** = measured pack voltage − (V_oc(SOC) − I × R_nominal). Negative means extra sag.
³ The fault's *consequence* severity. The diagnosis raises any fault to CRITICAL when predicted time-to-failure is under 30 min or a channel is already CRITICAL (`config/detector.json` → `severity_rules`).
⁴ Team estimates. Used for garage bay planning only.

## How the four are told apart

```
                       current UP?
                     /            \
                  yes              no
                  /                  \
     thermal residual UP?        drive temp UP?
        /         \                /        \
      yes          no            yes         no
       |            |             |           |
  bearing_wear  wheel_drag   cooling_fault   voltage residual DOWN under load?
                                                |
                                         battery_degradation
```

**The central case is bearing wear vs. wheel drag.** Both raise current and lower speed by the same mechanism (more load torque). They differ only in *where the extra energy ends up*: bearing friction turns into heat inside the hub; regolith drag does work on the soil outside it. Raw temperature is not enough. Drag also warms the hub a little, because copper loss grows with current squared (about +12 °C at failure in `TRAVERSE_EMPTY`). The thermal residual separates them: about +10 °C or more for bearing wear, about 0 for drag.

**Low battery is not battery degradation.** A flat pack has low voltage but a normal *residual*, because the model already expects a low V_oc at low SOC. That is why `battery_soc_pct` and `battery_current_a` are in the channel list.

## Injected magnitudes (team estimates)

Each fault changes one generator parameter, from its healthy value at injection to `at_failure` when progress `p` reaches 1. `at_failure` is chosen so the primary channel reaches its CRITICAL limit in `TRAVERSE_EMPTY` at thermal steady state (hand-computed from the equations in [DECISIONS.md §4](DECISIONS.md#4-physical-relationships-the-generator-must-obey); the generator tests must confirm it).

| Fault | Parameter changed | Healthy → at failure | Primary channel (CRITICAL limit) | Default progression |
|---|---|---|---|---|
| bearing_wear | `bearing_friction_extra_nm` | 0 → 2.2 N·m | `wheel_{w}_temp_c` (baseline + 30 °C) | power, exponent 2 (accelerating) |
| wheel_drag | `drag_torque_extra_nm` | 0 → 4.0 N·m | `wheel_{w}_current_a` (baseline + 2.0 A) | linear |
| cooling_fault | `r_th_multiplier` | 1.0 → 3.2 × | `wheel_{w}_temp_c` (baseline + 30 °C) | linear |
| battery_degradation | `r_int_multiplier` | 1.0 → 5.5 × | `battery_voltage_v` (model − 1.0 V) | power, exponent 1.5 |

Scenario time compression: real bearing and battery degradation take weeks to months. Our scenarios compress it into hours so a demo fits in one sitting. The *shape* of each fault is what we test, not its real-world duration.

## Not covered at PDR

- Joint / actuator faults ("abnormal joint current" in Mission 4). The lift actuator is monitored for status only. See open question Q3 in [DECISIONS.md](DECISIONS.md#10-open-questions-for-the-team).
- Faults on other robot types (P3, mining, construction). These come after PDR.
- Sensor faults (stuck or drifting sensors). Today a dropout is just `null`.
