"""Write the dashboard feed files.

Responsibility: after every batch, write runs/<run_id>/dashboard/ in exactly the
shapes of fixtures/healthy_fleet and fixtures/active_work_order:
    feed_index.json, fleet_board.json, robot_<ID>.json (one per robot),
    alerts.json, work_orders.json
All joining, formatting and limit-band maths happens HERE in Python, so the page
only draws arrays and strings. Every file is validated before it is written.

Write each file to a temporary name and rename it, so the browser never reads a
half-written file while a run is in progress.

STATUS: stubs. Build against the fixtures: when a real run's files validate and
look like the fixtures, the dashboard needs no changes.
"""

from pathlib import Path

import pandas as pd


def build_fleet_board(fleet_state: dict, snapshots: dict[str, dict], work_orders: dict[str, dict],
                      predictions: dict[str, dict], now_t_s: int, start_time_utc: str) -> dict:
    """fleet_board feed: summary counts + one row per robot, with a one-line headline."""
    raise NotImplementedError("build_fleet_board")


def build_robot_detail(robot_id: str, window_df: pd.DataFrame, snapshot: dict, fleet_robot: dict,
                       markers: list[dict], latest_prediction: dict | None, channels_cfg: dict,
                       modes_cfg: dict, detector_cfg: dict, now_t_s: int, start_time_utc: str) -> dict:
    """robot_<ID> feed: last 120 min as 1-minute means, with baseline and absolute limit
    bands per point (health.evaluate.absolute_limits) so plots match the evaluation."""
    raise NotImplementedError("build_robot_detail")


def build_alerts(events: list[dict], now_t_s: int, start_time_utc: str) -> dict:
    """alerts feed from the event log, newest first, operator-readable titles."""
    raise NotImplementedError("build_alerts")


def build_work_orders(garage: dict, work_orders: list[dict], now_t_s: int, start_time_utc: str) -> dict:
    """work_orders feed: garage + open orders in queue order, then recently closed ones."""
    raise NotImplementedError("build_work_orders")


def write_feed(obj: dict, schema_name: str, path: Path) -> None:
    """Validate obj against schemas/<schema_name>.schema.json, write to path via a temp
    file + rename."""
    raise NotImplementedError("write_feed")


def write_all(folder: Path, run_id: str, scenario: dict, now_t_s: int, fleet_board: dict,
              robot_details: dict[str, dict], alerts: dict, work_orders_feed: dict) -> None:
    """Write every feed plus feed_index.json (is_fixture false) into folder."""
    raise NotImplementedError("write_all")
