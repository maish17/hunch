"""Every fixture and scenario matches its JSON contract. REAL tests - pass today.

The dashboard is built against fixtures/, and the backend must produce files of the
same shape. If a contract changes, these tests fail until the fixtures are updated,
so the two sides cannot silently drift apart.
"""

import json
import unittest

from p4maint import configs
from p4maint.paths import FIXTURES_DIR, SCENARIOS_DIR
from schemas.validate import ContractError, default_targets, validate_file


class TestFixturesAndScenariosValidate(unittest.TestCase):
    def test_every_file_validates(self):
        targets = default_targets()
        self.assertGreater(len(targets), 30)
        for path in targets:
            with self.subTest(file=str(path.relative_to(FIXTURES_DIR.parent))):
                validate_file(path)

    def test_invalid_object_is_rejected(self):
        bad = FIXTURES_DIR / "contracts" / "work_order.example.json"
        work_order = json.loads(bad.read_text())
        work_order["severity"] = "SORT_OF_BAD"
        from schemas.validate import validate
        with self.assertRaises(ContractError):
            validate(work_order, "work_order")

    def test_both_scenarios_present(self):
        names = {p.name for p in SCENARIOS_DIR.glob("*.json")}
        self.assertIn("healthy_baseline.json", names)
        self.assertIn("bearing_wear_p2_02.json", names)


class TestFixtureContentsMatchConfig(unittest.TestCase):
    """Things a schema cannot express, because channel names are data-driven."""

    def setUp(self):
        self.names = configs.channel_names(configs.load_channels())

    def test_telemetry_batch_has_exactly_the_configured_channels(self):
        batch = json.loads((FIXTURES_DIR / "contracts" / "telemetry_batch.example.json").read_text())
        self.assertEqual(batch["channels"], self.names)
        for sample in batch["samples"]:
            self.assertEqual(set(sample) - {"t_s", "timestamp", "op_mode"}, set(self.names))

    def test_robot_detail_feeds_cover_every_channel(self):
        for path in FIXTURES_DIR.rglob("robot_*.json"):
            detail = json.loads(path.read_text())
            with self.subTest(file=path.name, folder=path.parent.name):
                self.assertEqual([c["channel"] for c in detail["series"]["channels"]], self.names)
                n = len(detail["series"]["t_s"])
                for c in detail["series"]["channels"]:
                    for key in ["value", "baseline", "warning_low", "warning_high", "critical_low", "critical_high"]:
                        self.assertEqual(len(c[key]), n, f"{c['channel']}.{key}")

    def test_fixture_sets_are_internally_consistent(self):
        for folder in ["healthy_fleet", "active_work_order"]:
            base = FIXTURES_DIR / folder
            index = json.loads((base / "feed_index.json").read_text())
            board = json.loads((base / "fleet_board.json").read_text())
            with self.subTest(folder=folder):
                for robot_id, file_name in index["files"]["robots"].items():
                    self.assertTrue((base / file_name).exists(), file_name)
                    detail = json.loads((base / file_name).read_text())
                    row = [r for r in board["robots"] if r["robot_id"] == robot_id][0]
                    self.assertEqual(row["health_status"], detail["snapshot"]["status"])

    def test_work_order_histories_follow_the_state_machine(self):
        sm = configs.load_state_machine()["work_order"]
        legal = {(t["from"], t["to"]) for t in sm["transitions"]}
        feed = json.loads((FIXTURES_DIR / "active_work_order" / "work_orders.json").read_text())
        for work_order in feed["work_orders"]:
            history = work_order["history"]
            self.assertIsNone(history[0]["from_status"])
            self.assertIn(history[0]["to_status"], sm["initial_states"])
            for entry in history[1:]:
                self.assertIn((entry["from_status"], entry["to_status"]), legal)
            self.assertEqual(history[-1]["to_status"], work_order["status"])


if __name__ == "__main__":
    unittest.main()
