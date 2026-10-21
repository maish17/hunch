"""Local dashboard server (p4maint/server.py): lists scenarios, generates runs on request."""

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from p4maint.server import ScenarioService, make_handler, overview, score_line
from tests.streams import single_robot_scenario


def wait_for(service: ScenarioService, timeout_s: float = 60) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = service.current()
        if job and job["state"] != "running":
            return job
        time.sleep(0.2)
    raise AssertionError("run did not finish")


class TestScenarioService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "scenarios").mkdir()
        scenario = single_robot_scenario([("TRAVERSE_EMPTY", 600)], 900)
        scenario["scenario_id"] = "tiny_test"
        (root / "scenarios" / "tiny_test.json").write_text(json.dumps(scenario))
        self.service = ScenarioService(scenarios_dir=root / "scenarios", runs_dir=root / "runs", serve_root=root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_scenarios_with_overview(self):
        items = self.service.list()
        self.assertEqual([i["id"] for i in items], ["tiny_test"])
        self.assertEqual(items[0]["overview"], "0.25 h, 1 rovers: no faults (checks for false alarms)")
        self.assertIsNone(items[0]["run"])

    def test_generate_then_view(self):
        status, body = self.service.start("tiny_test")
        self.assertEqual(status, 202)
        self.assertEqual(body["job"]["state"], "running")
        job = wait_for(self.service)
        self.assertEqual(job["state"], "done", job)
        run = self.service.list()[0]["run"]
        self.assertTrue(run["feed"].startswith("../runs/") and run["feed"].endswith("dashboard/feed_index.json"))
        self.assertEqual(run["score"], "0 false alarms")

    def test_regenerating_starts_clean(self):
        for _ in range(2):
            self.service.start("tiny_test")
            wait_for(self.service)
        events = Path(self.tmp.name, "runs").glob("*/events.jsonl")
        lines = next(events).read_text().splitlines()
        self.assertEqual(sum('"RUN_STARTED"' in line for line in lines), 1)

    def test_unknown_and_busy(self):
        self.assertEqual(self.service.start("../etc/passwd")[0], 404)
        self.assertEqual(self.service.start("tiny_test")[0], 202)
        self.assertEqual(self.service.start("tiny_test")[0], 409)
        wait_for(self.service)


class TestHttpApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "scenarios").mkdir()
        (root / "scenarios" / "tiny_test.json").write_text(json.dumps(single_robot_scenario([("IDLE", 60)], 120)))
        service = ScenarioService(scenarios_dir=root / "scenarios", runs_dir=root / "runs", serve_root=root)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def post(self, body: dict, origin: str | None = None) -> int:
        request = urllib.request.Request(self.base + "/api/generate", data=json.dumps(body).encode(), method="POST")
        if origin:
            request.add_header("Origin", origin)
        try:
            return urllib.request.urlopen(request).status
        except urllib.error.HTTPError as error:
            return error.code

    def test_scenarios_endpoint(self):
        data = json.loads(urllib.request.urlopen(self.base + "/api/scenarios").read())
        self.assertEqual(len(data["scenarios"]), 1)
        self.assertIsNone(data["job"])

    def test_rejects_other_websites_and_unknown_ids(self):
        self.assertEqual(self.post({"scenario": "tiny_test"}, origin="https://example.com"), 403)
        self.assertEqual(self.post({"scenario": "nope"}), 404)


class TestText(unittest.TestCase):
    def test_score_line(self):
        score = {"faults": [{"warning_lead_time_s": 2040.0, "diagnosis_correct": True}],
                 "false_alarms": {"anomalies": 0, "predictive_warnings": 0, "work_orders": 0}}
        self.assertEqual(score_line(score), "warned 34 min before failure, right diagnosis; 0 false alarms")
        score["faults"][0]["warning_lead_time_s"] = None
        self.assertTrue(score_line(score).startswith("missed"))

    def test_overview_names_the_fault(self):
        from p4maint.generator.scenario import load_scenario
        from p4maint.paths import SCENARIOS_DIR
        text = overview(load_scenario(SCENARIOS_DIR / "bearing_wear_p2_02.json"))
        self.assertEqual(text, "4 h, 5 rovers: wheel hub bearing wear on P2-02 (front-left wheel drive), starts T+1:00, fails T+3:30")


if __name__ == "__main__":
    unittest.main()
