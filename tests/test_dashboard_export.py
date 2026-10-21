"""Dashboard export (p4maint/dashboard_export/feeds.py): real runs produce the same
files, in the same shapes, as the hand-made fixtures the dashboard was built on."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from p4maint import configs, openloop
from p4maint.dashboard_export.feeds import minute_point
from p4maint.health.evaluate import absolute_limits
from schemas.validate import schema_name_for, validate_file
from tests.streams import CHANNELS, scenario_result, single_robot_scenario, slow


def load(folder: Path, name: str) -> dict:
    return json.loads((folder / name).read_text())


@slow
class TestFeedsFromARealRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = scenario_result("bearing_wear_p2_02")
        cls.folder = cls.result["dashboard"]

    def test_every_feed_file_exists_and_validates(self):
        index = load(self.folder, "feed_index.json")
        self.assertFalse(index["is_fixture"])
        names = ["feed_index.json", "fleet_board.json", "alerts.json", "work_orders.json"] + list(index["files"]["robots"].values())
        self.assertEqual(sorted(index["files"]["robots"]), ["P2-01", "P2-02", "P2-03", "P2-04", "P2-05"])
        for name in names:
            with self.subTest(file=name):
                self.assertIsNotNone(schema_name_for(self.folder / name))
                validate_file(self.folder / name)

    def test_robot_detail_series_and_bands(self):
        detail = load(self.folder, "robot_P2-02.json")
        n = len(detail["series"]["t_s"])
        self.assertEqual(n, 120, "last 2 hours at one point per minute")
        self.assertEqual([c["channel"] for c in detail["series"]["channels"]], configs.channel_names(CHANNELS))
        for channel in detail["series"]["channels"]:
            for key in ["value", "baseline", "warning_low", "warning_high", "critical_low", "critical_high"]:
                self.assertEqual(len(channel[key]), n, f"{channel['channel']}.{key}")
        temp = [c for c in detail["series"]["channels"] if c["channel"] == "wheel_fl_temp_c"][0]
        lines = absolute_limits(configs.get_channel(CHANNELS, "wheel_fl_temp_c"), temp["baseline"][-1])
        self.assertAlmostEqual(temp["warning_high"][-1], lines["warning_high"], places=1)
        self.assertGreater(temp["value"][-1] - temp["baseline"][-1], 15, "the failing wheel is past its warning line")

    def test_markers_show_alerts_and_prediction(self):
        markers = load(self.folder, "robot_P2-02.json")["markers"]
        kinds = {m["kind"] for m in markers}
        self.assertTrue({"ANOMALY", "PREDICTION", "PREDICTED_FAILURE"} <= kinds)
        self.assertEqual(load(self.folder, "robot_P2-01.json")["markers"], [])

    def test_alert_feed_newest_first_and_complete(self):
        alerts = load(self.folder, "alerts.json")["alerts"]
        times = [a["t_s"] for a in alerts]
        self.assertEqual(times, sorted(times, reverse=True))
        self.assertEqual(sum(a["kind"] == "ANOMALY" for a in alerts), len(self.result["anomalies"]))
        self.assertTrue(all("unknown" not in a["title"] for a in alerts if a["kind"] == "PREDICTION"))

    def test_fleet_board_matches_snapshots(self):
        board = load(self.folder, "fleet_board.json")
        for row in board["robots"]:
            self.assertEqual(row["health_status"], self.result["snapshots"][row["robot_id"]]["status"])
        self.assertEqual(board["summary"]["robots_total"], 5)
        self.assertEqual(board["summary"]["open_work_orders"], 0, "open loop: no work orders yet")


class TestExportDetails(unittest.TestCase):
    def test_minute_point_skips_the_mode_change_grace_period(self):
        evaluated = pd.DataFrame({
            "t_s": [0, 1, 2, 3], "op_mode": ["IDLE", "IDLE", "TRAVERSE_EMPTY", "TRAVERSE_EMPTY"],
            "channel": ["wheel_fl_current_a"] * 4, "value": [0.0, 9.0, 3.3, 3.3], "baseline": [0.0, 3.29, 3.29, 3.29],
            "in_grace": [False, True, False, False]})
        point = minute_point(evaluated)
        self.assertEqual(point["t_s"], 0)
        self.assertAlmostEqual(point["channels"]["wheel_fl_current_a"][0], 2.2)

    def test_dashboard_at_exports_that_moment(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenario = single_robot_scenario([("TRAVERSE_EMPTY", 600)], 1200)
            path = Path(tmp) / "scenario.json"
            path.write_text(json.dumps(scenario))
            result = openloop.run(path, write_telemetry=False, folder=Path(tmp) / "run", dashboard_at_t_s=600)
            board = load(result["dashboard"], "fleet_board.json")
            self.assertEqual(board["t_s"], 659)
            self.assertEqual(len(load(result["dashboard"], "robot_P2-01.json")["series"]["t_s"]), 11)


if __name__ == "__main__":
    unittest.main()
