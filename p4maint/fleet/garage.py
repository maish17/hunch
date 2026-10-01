"""P5 Repair Garage: bays and the priority queue.

Responsibility: own the garage_queue contract (schemas/garage_queue.schema.json).
Queue work orders in priority order (config/dispatch.json queue_priority: CRITICAL
first, then soonest predicted failure, then oldest), reserve a bay when one is free,
admit robots that arrive, and release them when repair is done. Garage capacity is
limited (dispatch.json garage.capacity, scenario may override).

STATUS: stubs.
"""

from pathlib import Path


def new_garage(dispatch_cfg: dict, capacity: int | None, now_t_s: int, start_time_utc: str) -> dict:
    """Empty garage_queue with `capacity` EMPTY bays named BAY-1, BAY-2, ..."""
    raise NotImplementedError("new_garage")


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
    raise NotImplementedError("save_garage")
