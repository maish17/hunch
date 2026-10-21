"""Rolling in-memory window per robot.

Responsibility: keep the most recent N seconds of rows for each robot, for any table
that has robot_id and t_s columns. The pipeline keeps two: raw telemetry and the
evaluated per-sample statuses. Trend fitting needs 30 min of history, and Parquet
cannot be read until the run's writer is closed, so look-back comes from here.
"""

import pandas as pd


class RollingWindow:
    """Last max_window_s seconds of rows for every robot."""

    def __init__(self, max_window_s: int) -> None:
        """max_window_s: the longest look-back any stage needs (the pipeline passes the
        larger of detector.json trend.fit_window_s and dispatch.json work_order_evidence.window_s)."""
        self.max_window_s = max_window_s
        self.frames: dict[str, pd.DataFrame] = {}

    def add(self, rows: pd.DataFrame) -> None:
        """Append rows (any robots) and drop rows older than the window, per robot."""
        for robot_id, new_rows in rows.groupby("robot_id"):
            if robot_id in self.frames:
                combined = pd.concat([self.frames[robot_id], new_rows], ignore_index=True)
            else:
                combined = new_rows.reset_index(drop=True)
            newest = combined["t_s"].max()
            self.frames[robot_id] = combined[combined["t_s"] > newest - self.max_window_s].reset_index(drop=True)

    def window(self, robot_id: str, seconds: int) -> pd.DataFrame:
        """This robot's rows for the last `seconds` seconds (may be shorter early in a run).
        An unknown robot gives an empty DataFrame."""
        frame = self.frames.get(robot_id)
        if frame is None or frame.empty:
            return pd.DataFrame()
        newest = frame["t_s"].max()
        return frame[frame["t_s"] > newest - seconds].reset_index(drop=True)
