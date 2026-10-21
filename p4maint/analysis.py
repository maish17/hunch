"""The ground system's per-batch analysis: Missions 1-4 in one place.

Responsibility: for every robot in a 60 s batch, in order:
    1. health.evaluate        status of every reading + health snapshot   (Mission 1)
    2. detect.anomaly         debounced anomaly events                    (Mission 2)
    3. diagnose.diagnosis     which fault, on which component             (Mission 4)
    4. predict.trend          time until the target channel hits CRITICAL (Mission 3)
    5. predict.prediction     the prediction contract, published only when it changes
Both p4maint/openloop.py (today) and p4maint/pipeline.py (once the fleet manager
exists) call this, so the analysis is written once. Ground-side code: it must never
see the answer key or config/generator.json (tests/test_answer_key_isolation.py).
"""

import pandas as pd

from p4maint.detect.anomaly import AnomalyDetector
from p4maint.diagnose.diagnosis import diagnose
from p4maint.health.evaluate import build_snapshot, evaluate_samples, new_baseline_state
from p4maint.ingest.history import RollingWindow
from p4maint.predict.prediction import build_prediction, new_prediction_id, should_publish
from p4maint.predict.trend import trend_for_channel
from p4maint.configs import get_channel


class GroundAnalysis:
    """State the analysis keeps between batches, for every robot."""

    def __init__(self, cfg: dict, start_time_utc: str) -> None:
        """cfg holds the loaded "channels", "modes", "faults" and "detector" configs."""
        self.cfg = cfg
        self.start = start_time_utc
        detector_cfg = cfg["detector"]
        self.look_back_s = max(detector_cfg["trend"]["fit_window_s"], detector_cfg["diagnosis"]["window_s"])
        self.telemetry = RollingWindow(self.look_back_s)
        self.evaluated = RollingWindow(self.look_back_s)
        self.baselines = new_baseline_state()
        self.detector = AnomalyDetector(detector_cfg, cfg["channels"], start_time_utc)
        self.next_prediction = 1
        self.published: dict[str, dict] = {}   # robot_id -> last published prediction

    def analyse_batch(self, batch: pd.DataFrame) -> dict[str, dict]:
        """Run steps 1-5 for every robot in the batch.

        Returns {robot_id: {"evaluated", "snapshot", "raised", "cleared", "diagnosis",
        "prediction", "published"}} ("evaluated" is this batch's per-sample table). "prediction" is the newest prediction (or None); "published" says
        whether it is new enough to announce (log PREDICTION_ISSUED).
        """
        cfg = self.cfg
        now_t_s = int(batch["t_s"].max())
        self.telemetry.add(batch)
        results = {}
        for robot_id in sorted(batch["robot_id"].unique()):
            evaluated = evaluate_samples(batch, robot_id, cfg["channels"], cfg["modes"], cfg["detector"], self.baselines)
            evaluated["robot_id"] = robot_id
            self.evaluated.add(evaluated)
            snapshot = build_snapshot(evaluated, robot_id, cfg["channels"], cfg["detector"], self.start, check=False)
            raised, cleared = self.detector.update(evaluated, robot_id, now_t_s)
            active = self.detector.active_anomalies(robot_id)

            evaluated_window = self.evaluated.window(robot_id, self.look_back_s)
            diagnosis = diagnose(robot_id, self.telemetry.window(robot_id, self.look_back_s), evaluated_window,
                                 active, cfg["channels"], cfg["faults"], cfg["detector"])
            prediction, published = None, False
            if diagnosis is not None:
                prediction = self._predict(robot_id, diagnosis, evaluated, evaluated_window, active, now_t_s)
                published = should_publish(self.published.get(robot_id), prediction, cfg["detector"])
                if published:
                    self.published[robot_id] = prediction
                    self.next_prediction += 1
            results[robot_id] = {"evaluated": evaluated, "snapshot": snapshot, "raised": raised, "cleared": cleared,
                                 "diagnosis": diagnosis, "prediction": prediction, "published": published}
        return results

    def _predict(self, robot_id: str, diagnosis: dict, evaluated: pd.DataFrame, evaluated_window: pd.DataFrame,
                 active: list[dict], now_t_s: int) -> dict:
        cfg = self.cfg
        target = get_channel(cfg["channels"], diagnosis["target_channel"])
        trend = trend_for_channel(evaluated_window, target, cfg["modes"], cfg["detector"], now_t_s)
        latest = evaluated[(evaluated["channel"] == target["name"])].sort_values("t_s")["baseline"].dropna()
        baseline = float(latest.iloc[-1]) if not latest.empty else None
        anomaly_ids = [event["anomaly_id"] for event in active
                       if event["component"] == diagnosis["component"] or event["channel"] == target["name"]]
        return build_prediction(new_prediction_id(self.next_prediction), robot_id, diagnosis, trend, baseline,
                                anomaly_ids, now_t_s, self.start, cfg["channels"], cfg["faults"], cfg["detector"])
