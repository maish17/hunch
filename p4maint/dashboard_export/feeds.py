"""Write the dashboard feed files.

Responsibility: write a folder in exactly the shapes of fixtures/healthy_fleet and
fixtures/active_work_order:
    feed_index.json, fleet_board.json, robot_<ID>.json (one per robot),
    alerts.json, work_orders.json
All joining, formatting and limit-band maths happens HERE in Python, so the page
only draws arrays and strings. Every file is validated before it is written, and
written to a temporary name then renamed, so the browser never reads half a file.

Time series come from minute_point(): one point per channel per 60 s batch (the mean
of the smoothed values outside the mode-change grace period), kept for the whole run
by the caller. Limit bands use health.evaluate.absolute_limits, so the plots always
match the evaluation.
"""

import json
import math
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from p4maint.configs import get_channel, get_fault
from p4maint.health.evaluate import absolute_limits
from schemas.validate import validate

DECIMALS = {"A": 3, "rad/s": 3, "degC": 2, "V": 3, "%": 1, "deg": 3}
LIMIT_KEYS = ["warning_low", "warning_high", "critical_low", "critical_high"]
DETAIL_WINDOW_S = 7200


def _iso(start_time_utc: str, t_s: float) -> str:
    start = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ")
    return (start + timedelta(seconds=int(t_s))).strftime("%Y-%m-%dT%H:%M:%SZ")


def _met(t_s: float) -> str:
    t_s = int(t_s)
    return f"T+{t_s // 3600}:{t_s % 3600 // 60:02d}"


def _round(value, units: str):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), DECIMALS.get(units, 3))


def component_name(component_id: str, channels_cfg: dict) -> str:
    """'wheel_fl_drive' -> 'front-left wheel drive' (the label before any bracket)."""
    for component in channels_cfg["hierarchy"]["components"]:
        if component["id"] == component_id:
            name = component["label"].split(" (")[0]
            return name[0].lower() + name[1:]
    return component_id


def minute_point(evaluated_batch: pd.DataFrame) -> dict:
    """One dashboard point per channel for a 60 s batch of one robot's evaluated samples.

    Returns {"t_s": first t_s of the batch, "op_mode": most common mode,
    "channels": {channel: (mean value, mean baseline)}}. Samples inside the mode-change
    grace period are left out (their smoothed values lag the step), unless that is all
    there is.
    """
    settled = evaluated_batch[~evaluated_batch["in_grace"]]
    if settled.empty:
        settled = evaluated_batch
    channels = {}
    for name, rows in settled.groupby("channel", sort=False):
        value = rows["value"].astype(float).mean()
        baseline = rows["baseline"].astype(float).mean()
        channels[name] = (None if math.isnan(value) else value, None if math.isnan(baseline) else baseline)
    mode = Counter(evaluated_batch["op_mode"]).most_common(1)[0][0]
    return {"t_s": int(evaluated_batch["t_s"].min()), "op_mode": mode, "channels": channels}


def markers_for(robot_id: str, anomalies: list[dict], predictions: list[dict], is_warning) -> list[dict]:
    """Event markers for one robot's plots: every alert, the first prediction that names a
    fault, the first predictive warning, and the latest predicted failure time.
    is_warning is predict.prediction.is_predictive_warning with its config bound."""
    markers = []
    for event in anomalies:
        if event["robot_id"] == robot_id:
            markers.append({"t_s": event["t_s"], "kind": "ANOMALY", "channel": event["channel"],
                            "severity": event["severity"], "label": event["message"]})
    mine = [p for p in predictions if p["robot_id"] == robot_id]
    named = [p for p in mine if p["fault_mode"] != "unknown"]
    if named:
        first = named[0]
        markers.append({"t_s": first["made_at_t_s"], "kind": "PREDICTION", "channel": first["target_channel"],
                        "severity": first["severity"], "label": f"{first['fault_mode']} suspected"})
    warnings = [p for p in mine if is_warning(p)]
    if warnings:
        first = warnings[0]
        markers.append({"t_s": first["made_at_t_s"], "kind": "PREDICTION", "channel": first["target_channel"],
                        "severity": first["severity"],
                        "label": f"Predictive warning: about {first['predicted_ttf_s'] / 60:.0f} min to failure"})
    if mine and mine[-1]["predicted_failure_t_s"] is not None:
        latest = mine[-1]
        markers.append({"t_s": latest["predicted_failure_t_s"], "kind": "PREDICTED_FAILURE",
                        "channel": latest["target_channel"], "severity": latest["severity"], "label": "Predicted failure"})
    return sorted(markers, key=lambda m: m["t_s"])


def headline_for(fleet_robot: dict, snapshot: dict, prediction: dict | None, now_t_s: int,
                 channels_cfg: dict, faults_cfg: dict) -> str:
    """One plain line for the robot's card."""
    if prediction is not None and prediction["fault_mode"] != "unknown":
        fault = get_fault(faults_cfg, prediction["fault_mode"])["label"]
        where = component_name(prediction["component"], channels_cfg)
        if prediction["predicted_failure_t_s"] is None:
            return f"{fault} suspected ({where})"
        left = prediction["predicted_failure_t_s"] - now_t_s
        if left <= 0:
            return f"{fault} suspected ({where}) - past its predicted failure time"
        return f"{fault} suspected ({where}) - about {left / 60:.0f} min to predicted failure"
    if snapshot["status"] in ("WARNING", "CRITICAL"):
        worst = [ch for sub in snapshot["subsystems"] for comp in sub["components"] for ch in comp["channels"]
                 if ch["status"] == snapshot["status"]]
        label = get_channel(channels_cfg, worst[0]["channel"])["label"] if worst else "A reading"
        return f"{label} {snapshot['status']}"
    if fleet_robot["status"] == "STANDBY":
        return "Standby - ready" if fleet_robot["standby"] else "Standby"
    return "All channels normal"


def build_fleet_board(fleet_state: dict, snapshots: dict[str, dict], predictions: dict[str, dict],
                      state_machine_cfg: dict, channels_cfg: dict, faults_cfg: dict, now_t_s: int,
                      start_time_utc: str) -> dict:
    """fleet_board feed: summary counts + one row per robot, with a one-line headline.
    predictions maps robot_id -> that robot's latest published prediction."""
    labels = {mission["mission_id"]: mission["label"] for mission in fleet_state["missions"]}
    states = state_machine_cfg["robot"]["states"]
    rows = []
    for robot in fleet_state["robots"]:
        snapshot = snapshots[robot["robot_id"]]
        rows.append({
            "robot_id": robot["robot_id"], "robot_type": robot["robot_type"], "status": robot["status"],
            "status_label": states[robot["status"]]["label"], "mission_id": robot["mission_id"],
            "mission_label": labels.get(robot["mission_id"]), "op_mode": snapshot["op_mode"],
            "health_status": robot["health_status"], "health_score": robot["health_score"],
            "soc_pct": robot["soc_pct"], "location_zone": robot["location"]["zone"], "standby": robot["standby"],
            "subsystems": {s["subsystem"]: s["status"] for s in snapshot["subsystems"]},
            "open_work_order_id": robot["open_work_order_id"],
            "headline": headline_for(robot, snapshot, predictions.get(robot["robot_id"]), now_t_s, channels_cfg, faults_cfg),
        })
    statuses = [robot["status"] for robot in fleet_state["robots"]]
    summary = {
        "robots_total": len(rows),
        "in_service": sum(states[s]["in_service"] for s in statuses),
        "standby_available": sum(robot["standby"] for robot in fleet_state["robots"]),
        "in_maintenance": sum(s in ("MAINTENANCE_REQUIRED", "EN_ROUTE_P5", "IN_GARAGE") for s in statuses),
        "open_work_orders": sum(robot["open_work_order_id"] is not None for robot in fleet_state["robots"]),
        "missions_uncovered": sum(not mission["covered"] for mission in fleet_state["missions"]),
    }
    return {"schema_version": "1.0.0", "feed_type": "fleet_board", "t_s": now_t_s,
            "sim_time": _iso(start_time_utc, now_t_s), "summary": summary, "robots": rows}


def build_robot_detail(robot_id: str, minute_points: list[dict], snapshot: dict, fleet_robot: dict,
                       markers: list[dict], latest_prediction: dict | None, channels_cfg: dict,
                       now_t_s: int, start_time_utc: str) -> dict:
    """robot_<ID> feed: the last DETAIL_WINDOW_S (2 h) of minute points, with baseline and
    absolute limit bands per point."""
    points = [p for p in minute_points if p["t_s"] > now_t_s - DETAIL_WINDOW_S]
    series = {"t_s": [p["t_s"] for p in points], "op_mode": [p["op_mode"] for p in points], "channels": []}
    for channel in channels_cfg["channels"]:
        name, units = channel["name"], channel["units"]
        entry = {"channel": name, "label": channel["label"], "units": units, "component": channel["component"],
                 "subsystem": channel["subsystem"], "value": [], "baseline": []}
        for key in LIMIT_KEYS:
            entry[key] = []
        for point in points:
            value, baseline = point["channels"].get(name, (None, None))
            entry["value"].append(_round(value, units))
            entry["baseline"].append(_round(baseline, units))
            lines = absolute_limits(channel, baseline)
            for key in LIMIT_KEYS:
                entry[key].append(_round(lines[key], units))
        series["channels"].append(entry)
    return {"schema_version": "1.0.0", "feed_type": "robot_detail", "robot_id": robot_id, "t_s": now_t_s,
            "sim_time": _iso(start_time_utc, now_t_s), "status": fleet_robot["status"],
            "mission_id": fleet_robot["mission_id"], "op_mode": snapshot["op_mode"], "snapshot": snapshot,
            "series": series, "markers": markers, "latest_prediction": latest_prediction,
            "open_work_order_id": fleet_robot["open_work_order_id"]}


ALERT_KINDS = {"ANOMALY_RAISED": "ANOMALY", "PREDICTION_ISSUED": "PREDICTION", "WORK_ORDER_CREATED": "WORK_ORDER",
               "ROBOT_STATUS_CHANGED": "STATUS_CHANGE", "STANDBY_SELECTED": "STANDBY_SWAP"}


def build_alerts(events: list[dict], now_t_s: int, start_time_utc: str) -> dict:
    """alerts feed from the event log, newest first. Predictions that do not name a fault
    yet ("unknown") are left out to keep the operator's list short."""
    alerts = []
    for event in events:
        kind = ALERT_KINDS.get(event["type"])
        if kind is None:
            continue
        payload, refs = event["payload"], event["refs"]
        if kind == "PREDICTION" and payload.get("fault_mode") == "unknown":
            continue
        if kind == "ANOMALY":
            detail = f"{payload['subsystem']} / {payload['component']}; began {_met(payload['t_s'])}"
        elif kind == "PREDICTION":
            when = ("no time-to-failure yet" if payload["predicted_failure_t_s"] is None
                    else f"predicted failure {_met(payload['predicted_failure_t_s'])}")
            detail = f"Confidence {payload['confidence']:.2f}; {when}"
        else:
            detail = ""
        severity = payload.get("severity", "INFO") if kind in ("ANOMALY", "PREDICTION", "WORK_ORDER") else "INFO"
        alerts.append({
            "alert_id": event["event_id"], "t_s": event["t_s"], "at": event["at"], "kind": kind,
            "severity": severity, "robot_id": event["robot_id"], "subsystem": payload.get("subsystem"),
            "channel": payload.get("channel", payload.get("target_channel")), "title": event["summary"],
            "detail": detail,
            "ref_id": refs.get("anomaly_id") or refs.get("prediction_id") or refs.get("work_order_id")
                      or refs.get("replacement_robot_id"),
        })
    alerts.sort(key=lambda a: (a["t_s"], a["alert_id"]), reverse=True)
    return {"schema_version": "1.0.0", "feed_type": "alerts", "t_s": now_t_s,
            "sim_time": _iso(start_time_utc, now_t_s), "alerts": alerts}


def build_work_orders(garage: dict, work_orders: list[dict], now_t_s: int, start_time_utc: str) -> dict:
    """work_orders feed: garage + open orders in queue order, then recently closed ones."""
    return {"schema_version": "1.0.0", "feed_type": "work_orders", "t_s": now_t_s,
            "sim_time": _iso(start_time_utc, now_t_s), "garage": garage, "work_orders": work_orders}


def write_feed(obj: dict, schema_name: str, path: Path, compact: bool = False) -> None:
    """Validate obj against schemas/<schema_name>.schema.json, write to path via a temp
    file + rename. compact=True (robot detail files) drops the indentation, which would
    otherwise put every number of every series on its own line."""
    validate(obj, schema_name)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    text = json.dumps(obj, separators=(",", ":")) if compact else json.dumps(obj, indent=2)
    temporary.write_text(text + "\n")
    os.replace(temporary, path)


def write_all(folder: Path, run_id: str, scenario: dict, now_t_s: int, fleet_board: dict,
              robot_details: dict[str, dict], alerts: dict, work_orders_feed: dict, label: str) -> Path:
    """Write every feed plus feed_index.json (is_fixture false) into folder. Returns the
    index path."""
    folder = Path(folder)
    write_feed(fleet_board, "dashboard_fleet_board", folder / "fleet_board.json")
    write_feed(alerts, "dashboard_alerts", folder / "alerts.json")
    write_feed(work_orders_feed, "dashboard_work_orders", folder / "work_orders.json")
    robot_files = {}
    for robot_id, detail in sorted(robot_details.items()):
        robot_files[robot_id] = f"robot_{robot_id}.json"
        write_feed(detail, "dashboard_robot_detail", folder / robot_files[robot_id], compact=True)
    index = {"schema_version": "1.0.0", "feed_type": "index", "run_id": run_id, "scenario_id": scenario["scenario_id"],
             "label": label, "is_fixture": False, "t_s": now_t_s, "sim_time": _iso(scenario["start_time_utc"], now_t_s),
             "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "files": {"fleet_board": "fleet_board.json", "alerts": "alerts.json",
                       "work_orders": "work_orders.json", "robots": robot_files}}
    write_feed(index, "dashboard_index", folder / "feed_index.json")
    return folder / "feed_index.json"


def export_run(folder: Path, run_id: str, scenario: dict, now_t_s: int, fleet_state: dict, garage: dict,
               work_orders: list[dict], snapshots: dict[str, dict], minute_points: dict[str, list[dict]],
               anomalies: list[dict], predictions: list[dict], events: list[dict], cfg: dict, label: str) -> Path:
    """Build every feed for a run and write the folder. Used by p4maint/openloop.py and
    p4maint/pipeline.py.

    predictions is every published prediction in order; minute_points maps robot_id to
    that robot's minute_point() list; cfg holds "channels", "faults", "detector" and
    "state_machine". Returns the feed_index.json path.
    """
    from p4maint.predict.prediction import is_predictive_warning

    def is_warning(prediction):
        return is_predictive_warning(prediction, cfg["detector"])

    start = scenario["start_time_utc"]
    latest = {}
    for prediction in predictions:
        latest[prediction["robot_id"]] = prediction
    board = build_fleet_board(fleet_state, snapshots, latest, cfg["state_machine"], cfg["channels"],
                              cfg["faults"], now_t_s, start)
    details = {}
    for robot in fleet_state["robots"]:
        robot_id = robot["robot_id"]
        details[robot_id] = build_robot_detail(robot_id, minute_points.get(robot_id, []), snapshots[robot_id], robot,
                                               markers_for(robot_id, anomalies, predictions, is_warning),
                                               latest.get(robot_id), cfg["channels"], now_t_s, start)
    return write_all(folder, run_id, scenario, now_t_s, board, details, build_alerts(events, now_t_s, start),
                     build_work_orders(garage, work_orders, now_t_s, start), label)
