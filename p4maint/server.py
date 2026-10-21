"""Local dashboard server: serves the repo AND lets the dashboard generate runs.

    make dashboard          (or: python -m p4maint.server --port 8000)

Then open http://localhost:8000/dashboard/ and use the "Scenarios" panel: each
scenario has a one-line overview, its last result, a Generate button (runs it with
p4maint.openloop in the background, about 20 s) and a View button.

It is Python's built-in file server plus three small JSON endpoints:
    GET  /api/scenarios   every scenario: overview, last run (feed link, score line)
    POST /api/generate    {"scenario": "<scenario_id>"} -> start a run (one at a time)
    GET  /api/job         the current or last run: running / done / failed
Only listens on 127.0.0.1, so nothing outside this computer can reach it. Standard
library only - no extra dependencies. GitHub Pages has no server, so the public
website shows pre-generated runs instead (make site-data).
"""

import argparse
import json
import shutil
import threading
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from p4maint import configs, openloop, paths
from p4maint.dashboard_export.feeds import component_name
from p4maint.generator.scenario import load_scenario, make_run_id


def hm(t_s: float) -> str:
    t_s = int(t_s)
    return f"T+{t_s // 3600}:{t_s % 3600 // 60:02d}"


def overview(scenario: dict) -> str:
    """One plain line describing a scenario, e.g.
    '4 h, 5 rovers: wheel hub bearing wear on P2-02 (front-left wheel drive), starts T+1:00, fails T+3:30'."""
    faults_cfg, channels_cfg = configs.load_faults(), configs.load_channels()
    head = f"{scenario['duration_s'] / 3600:g} h, {len(scenario['robots'])} rovers"
    if not scenario["faults"]:
        return f"{head}: no faults (checks for false alarms)"
    parts = []
    for fault in scenario["faults"]:
        label = configs.get_fault(faults_cfg, fault["fault_type"])["label"].lower()
        where = component_name(fault["component"], channels_cfg)
        parts.append(f"{label} on {fault['robot_id']} ({where}), starts {hm(fault['inject_at_s'])}, "
                     f"fails {hm(fault['inject_at_s'] + fault['time_to_failure_s'])}")
    return f"{head}: " + "; ".join(parts)


def score_line(score: dict) -> str:
    """One plain line from score.json."""
    false_alarms = sum(score["false_alarms"].values())
    if not score["faults"]:
        return f"{false_alarms} false alarms"
    parts = []
    for fault in score["faults"]:
        if fault["warning_lead_time_s"] is None:
            parts.append("missed (no early warning)")
        else:
            diagnosis = "right diagnosis" if fault["diagnosis_correct"] else "wrong diagnosis first"
            parts.append(f"warned {fault['warning_lead_time_s'] / 60:.0f} min before failure, {diagnosis}")
    return "; ".join(parts) + f"; {false_alarms} false alarms"


class ScenarioService:
    """Lists scenarios and runs one at a time in a background thread."""

    def __init__(self, scenarios_dir: Path = paths.SCENARIOS_DIR, runs_dir: Path = paths.RUNS_DIR,
                 serve_root: Path = paths.REPO_ROOT) -> None:
        self.scenarios_dir = Path(scenarios_dir).resolve()
        self.runs_dir = Path(runs_dir).resolve()
        self.serve_root = Path(serve_root).resolve()
        self.lock = threading.Lock()
        self.job: dict | None = None

    def _path(self, scenario_id: str) -> Path | None:
        """The scenario file for an id, or None. Only ids of files that exist are accepted."""
        for path in sorted(self.scenarios_dir.glob("*.json")):
            if path.stem == scenario_id:
                return path
        return None

    def run_folder(self, scenario: dict) -> Path:
        return self.runs_dir / f"{make_run_id(scenario)}__open_loop"

    def list(self) -> list[dict]:
        items = []
        for path in sorted(self.scenarios_dir.glob("*.json")):
            scenario = load_scenario(path)
            folder = self.run_folder(scenario)
            run = None
            index_path = folder / "dashboard" / "feed_index.json"
            score_path = folder / "score.json"
            if index_path.exists() and score_path.exists():
                index = json.loads(index_path.read_text())
                feed = None
                if self.serve_root in index_path.resolve().parents:
                    feed = "../" + str(index_path.resolve().relative_to(self.serve_root))
                run = {"feed": feed, "generated_at": index["generated_at"],
                       "score": score_line(json.loads(score_path.read_text()))}
            items.append({"id": path.stem, "overview": overview(scenario), "description": scenario["description"],
                          "run": run})
        return items

    def start(self, scenario_id: str) -> tuple[int, dict]:
        """(HTTP status, body). 202 started, 404 unknown scenario, 409 another run is going."""
        path = self._path(scenario_id)
        if path is None:
            return 404, {"error": f"No scenario called {scenario_id!r}"}
        with self.lock:
            if self.job and self.job["state"] == "running":
                return 409, {"error": f"Already generating {self.job['scenario']}; wait for it to finish", "job": self.job}
            self.job = {"scenario": scenario_id, "state": "running", "message": "Generating...",
                        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "seconds": 0.0}
            job = self.job
        threading.Thread(target=self._run, args=(path, job), daemon=True).start()
        return 202, {"job": job}

    def _run(self, path: Path, job: dict) -> None:
        started = time.time()
        try:
            scenario = load_scenario(path)
            folder = self.run_folder(scenario)
            if folder.exists():  # start clean: the event log must not mix two runs
                assert self.runs_dir.resolve() in folder.resolve().parents, "refusing to delete outside the runs folder"
                shutil.rmtree(folder)
            result = openloop.run(path, folder=folder)
            job["state"] = "done"
            job["message"] = score_line(result["score"])
        except Exception as error:  # report any failure to the page instead of dying silently
            job["state"] = "failed"
            job["message"] = f"{type(error).__name__}: {error}"
        job["seconds"] = round(time.time() - started, 1)

    def current(self) -> dict | None:
        job = self.job
        if job and job["state"] == "running":
            job = dict(job, seconds=round((datetime.now(timezone.utc) - datetime.strptime(
                job["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds(), 1))
        return job


def make_handler(service: ScenarioService):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(service.serve_root), **kwargs)

        def _send_json(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def end_headers(self):
            # Feed files change when a run is regenerated; never let the browser keep old ones.
            if self.path.endswith(".json"):
                self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path.split("?")[0] == "/api/scenarios":
                return self._send_json(200, {"scenarios": service.list(), "job": service.current()})
            if self.path.split("?")[0] == "/api/job":
                return self._send_json(200, {"job": service.current()})
            return super().do_GET()

        def do_POST(self):
            if self.path != "/api/generate":
                return self._send_json(404, {"error": "unknown endpoint"})
            origin = self.headers.get("Origin")
            if origin and not origin.startswith(("http://localhost", "http://127.0.0.1")):
                return self._send_json(403, {"error": "only this computer's dashboard may start runs"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                scenario_id = json.loads(self.rfile.read(length) or b"{}").get("scenario", "")
            except (ValueError, AttributeError):
                return self._send_json(400, {"error": "send JSON like {\"scenario\": \"bearing_wear_p2_02\"}"})
            status, body = service.start(str(scenario_id))
            return self._send_json(status, body)

        def log_message(self, format, *args):
            if "/api/job" not in self.path:  # the page polls this every 2 s; keep the terminal readable
                super().log_message(format, *args)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the dashboard with scenario generation.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(ScenarioService()))
    print(f"Dashboard:  http://localhost:{args.port}/dashboard/   (website: http://localhost:{args.port}/site/)")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
