"""P5 Repair Garage: bays and the priority queue.

Responsibility: own the garage_queue contract (schemas/garage_queue.schema.json).
Queue work orders in priority order (config/dispatch.json queue_priority: CRITICAL
first, then soonest predicted failure, then oldest), reserve a bay when one is free,
admit robots that arrive, and release them when repair is done. Garage capacity is
limited (dispatch.json garage.capacity, scenario may override).

STATUS: new_garage and save_garage are done (the dashboard needs them); queueing,
reserving, admitting and releasing are Mission 6 stubs.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from schemas.validate import validate


def new_garage(dispatch_cfg: dict, capacity: int | None, now_t_s: int, start_time_utc: str) -> dict:
    """Empty garage_queue with `capacity` EMPTY bays named BAY-1, BAY-2, ...
    capacity None -> config/dispatch.json garage.capacity."""
    settings = dispatch_cfg["garage"]
    capacity = capacity or settings["capacity"]
    start = datetime.strptime(start_time_utc, "%Y-%m-%dT%H:%M:%SZ")
    bays = [{"bay_id": f"BAY-{n}", "state": "EMPTY", "robot_id": None, "work_order_id": None,
             "since_t_s": None, "est_release_t_s": None} for n in range(1, capacity + 1)]
    return {"schema_version": "1.0.0", "garage_id": settings["garage_id"], "t_s": now_t_s,
            "generated_at": (start + timedelta(seconds=now_t_s)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "capacity": capacity, "bays": bays, "queue": []}


def enqueue(garage: dict, work_order: dict, now_t_s: int, dispatch_cfg: dict) -> None:
    """Add a work order to the queue, then reorder the whole queue by priority and
    renumber positions from 1."""
    raise NotImplementedError("enqueue")


def free_bay(garage: dict) -> str | None:
    """bay_id of the first EMPTY bay, or None if the garage is full."""
    raise NotImplementedError("free_bay")


def reserve_next(garage: dict, now_t_s: int, dispatch_cfg: dict) -> dict | None:
    """If a bay is free and the queue is not empty, pop the front work order, mark the
    bay RESERVED for it and return {"work_order_id", "robot_id", "bay_id", "eta_t_s"}
    (eta = now + travel_time_to_p5_s). Otherwise None."""
    raise NotImplementedError("reserve_next")


def admit(garage: dict, robot_id: str, now_t_s: int, est_repair_s: float) -> None:
    """Robot arrived: its RESERVED bay becomes OCCUPIED, est_release_t_s = now + est_repair_s."""
    raise NotImplementedError("admit")


def release(garage: dict, robot_id: str) -> str:
    """Repair done: empty the robot's bay. Returns the work_order_id that was in it."""
    raise NotImplementedError("release")


def save_garage(garage: dict, folder: Path) -> Path:
    """Validate, then write <folder>/garage_queue.json. Returns the path."""
    validate(garage, "garage_queue")
    path = Path(folder) / "garage_queue.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(garage, indent=2) + "\n")
    return path
