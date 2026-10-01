"""Rolling in-memory window per robot.

Responsibility: keep the most recent N seconds of rows for each robot, for any table
that has robot_id and t_s columns. The pipeline keeps two: raw telemetry and the
evaluated per-sample statuses. Trend fitting needs 30 min of history, and Parquet
cannot be read until the run's writer is closed, so look-back comes from here.

STATUS: stubs.
"""

import pandas as pd


class RollingWindow:
    """Last max_window_s seconds of rows for every robot."""

    def __init__(self, max_window_s: int) -> None:
        """max_window_s: the longest look-back any stage needs (the pipeline passes the
        larger of detector.json trend.fit_window_s and dispatch.json work_order_evidence.window_s)."""
        raise NotImplementedError("RollingWindow.__init__")

    def add(self, rows: pd.DataFrame) -> None:
        """Append rows (any robots) and drop rows older than the window, per robot."""
        raise NotImplementedError("RollingWindow.add")

    def window(self, robot_id: str, seconds: int) -> pd.DataFrame:
        """This robot's rows for the last `seconds` seconds (may be shorter early in a run)."""
        raise NotImplementedError("RollingWindow.window")
