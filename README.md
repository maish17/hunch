# P4 Predictive Maintenance: lunar robot fleet health

NASA HUNCH 2026-27 SFT · LLASO Project 4 (`LLASO-P4-AI-MAINT-2026`)

An AI system that reads lunar transport-robot telemetry, flags problems, predicts failures before they happen, writes work orders for the P5 Repair Garage and puts a standby robot into service, without a human watching. PDR scope is **Missions 1-6** for the **P2 transport robot**, using **rule-based thresholds plus trend extrapolation** (no machine learning).

> **Status: Missions 1-4 working, dashboard on real output.** The **telemetry generator, storage, event log, state machine, health checks (Mission 1), anomaly alerts (Mission 2), trend prediction (Mission 3), diagnosis (Mission 4), scoring and the dashboard export work** (`make detect`). Work orders and the fleet manager's decisions (Missions 5-6) are **stubs for the team to write**. Running a scenario stops at the first unbuilt stage and names it. That message is our progress meter.

**Website:** https://maish17.github.io/hunch/ (source in [`site/`](site/README.md)).

## Quick start

Needs Python 3.11+ and `make` (macOS/Linux; on Windows, copy the commands out of the `Makefile`).

```bash
make setup
```

```bash
make validate
```

```bash
make test
```

```bash
make dashboard
```

Then open http://localhost:8000/dashboard/ and press **Scenarios** (top right). Each scenario has a one-line overview and its last result; press **Generate** to run it (about 20 s) and it opens in the dashboard by itself, or **View** to open the last run. No other commands needed. The website is at http://localhost:8000/site/.

```bash
make demo
```

This runs `scenarios/bearing_wear_p2_02.json` end to end. Today it stops at `initial_fleet_state`, the first Mission 6 stub.

To run everything that works today (generator, Missions 1-4, scoring) on a scenario:

```bash
make detect
```

It prints a timeline of alerts and predictions, each robot's final health, the score, and a link to open the dashboard on that run. The score shows: how long before the true failure the first predictive warning came, whether the diagnosis was right, and the false-alarm counts. It writes `runs/<id>__open_loop/` (telemetry, answer key, `events.jsonl`, health snapshots, fleet state, `score.json`, and `dashboard/` feeds). Add `--dashboard-at <seconds>` via `python -m p4maint.openloop` to show the fleet at a chosen moment instead of the end. Try `SCENARIO=scenarios/wheel_drag_p2_01.json` (or `cooling_fault_p2_03`, `battery_degradation_p2_02`, `healthy_baseline`). `make generate` does the telemetry part only.

### Results so far (simulated data, `make detect` on each scenario)

| Scenario | First predictive warning before failure | Diagnosis | Predicted failure time | False alarms |
|---|---|---|---|---|
| `healthy_baseline` | none needed | - | - | 0 alerts, 0 predictions |
| `bearing_wear_p2_02` | 34 min | bearing wear (correct) | 23 min late (straight line vs accelerating wear) | 0 |
| `wheel_drag_p2_01` | 49 min | wheel drag (correct) | 10 min late | 0 |
| `cooling_fault_p2_03` | 56 min | cooling fault (correct) | 3 min late | 0 |
| `battery_degradation_p2_02` | 51 min | battery degradation (correct) | 9 min late | 0 |

Target (HUNCH excellence example): 15 min. No run ever announced the wrong fault; while the evidence was still forming it said "unknown". All of this is one seed per scenario on our own simulator, so treat it as a working demonstration, not a measured accuracy.

| Command | What it does |
|---|---|
| `make setup` | Create `.venv` and install pandas, numpy, pyarrow, jsonschema |
| `make validate` | Check config, scenarios and every fixture against `schemas/` |
| `make generate` | Simulate telemetry only (open loop): Parquet + answer key in `runs/<id>__open_loop/` |
| `make detect` | Generator + Missions 1-4 + scoring, open loop, with a printed timeline and score |
| `make test` | 127 real tests pass now (about 2 min); 16 Mission 5-6 stubs show as *skipped* until built |
| `make test-fast` | Same, skipping the five whole-scenario runs (about 10 s) |
| `make site-data` | Re-run all five scenarios and rewrite the website demo data in `site/demo/generated/` (about 2 min). Do this after changing the model, then commit |
| `make demo` / `make healthy` | Run the bearing-wear / healthy scenario: `python run_scenario.py <scenario>` |
| `make dashboard` | Dashboard + website at http://localhost:8000 (`p4maint/server.py`). The dashboard's **Scenarios** button generates and opens runs |
| `make clean` | Delete `runs/` and caches |

## Architecture

```
 scenarios/*.json ──► GENERATOR ─────────────────────────────► answer_key/ground_truth.json
 (seed, robots,       physics E1-E13,                                │  (only scoring reads it)
  missions, faults)   closed loop: reads fleet state each batch      │
                          │ 60 s batches @ 1 Hz        [SENSE, ENCODE]│
                          ▼                                          │
                       INGEST ──► telemetry.parquet   [TRANSMIT, STORE]
                          │ rolling window
                          ▼
   HEALTH (M1) ─► DETECT (M2) ─► DIAGNOSE (M4) + PREDICT (M3)          [ANALYZE]
   status vs       anomaly        which fault?     time to failure
   mode baseline   events         (residuals)      (trend → CRITICAL line)
                          │ prediction (+ evidence)
                          ▼
   WORK ORDERS (M5) ─► FLEET + GARAGE (M6) ──► simulator (closed loop)  [UPDATE TWIN, DECIDE & ACT]
   P5 hand-off          state machine, queue,
                        standby swap
          │                   │
          ▼                   ▼
   events.jsonl (append-only decision record)  ──►  DASHBOARD FEEDS ──► dashboard/ (static page)
                                                                         │
   SCORING ◄── answer key + events ──► score.json (warning lead time) ◄──┘
```

Everything that shapes behaviour is in `config/`. Every object that crosses a boundary has a contract in `schemas/`.

## Module map

| Path | Responsibility | Status |
|---|---|---|
| `config/channels.json` | The 17 channels, limits, hierarchy. **Single source of every threshold.** | done |
| `config/modes.json` | 5 operating modes, generator inputs, per-mode baselines | done |
| `config/faults.json` | The 4 fault types: physics effect, signature, severity, action | done |
| `config/generator.json` | World-truth physics and noise (generator only) | done |
| `config/detector.json` | Detection, trend and diagnosis tuning | done |
| `config/state_machine.json` | Robot and work-order states and legal transitions | done |
| `config/dispatch.json` | P5 capacity, queue priority, work-order triggers, standby rule | done |
| `schemas/` + `schemas/validate.py` | 17 JSON Schemas + validation helper/CLI | done |
| `fixtures/` | Example instances of every contract, two complete dashboard feed sets | done |
| `scenarios/` | `healthy_baseline` plus one scenario per fault: `bearing_wear_p2_02`, `wheel_drag_p2_01`, `cooling_fault_p2_03`, `battery_degradation_p2_02` | done |
| `p4maint/configs.py`, `p4maint/paths.py` | Config loading, file locations | done |
| `p4maint/generator/` | Scenario loading and checks, physics, faults, noise, closed-loop simulator, answer key, `python -m p4maint.generator` | done |
| `p4maint/ingest/` | Parquet store, telemetry batches, rolling window | done |
| `p4maint/health/` | Mission 1: status per channel vs mode baseline, roll-up | done |
| `p4maint/detect/` | Mission 2: debounced anomaly events | done |
| `p4maint/predict/` | Mission 3: trend fit, time-to-failure, prediction contract | done |
| `p4maint/diagnose/` | Mission 4: residuals, signature matching | done |
| `p4maint/workorders/` | Mission 5: work orders | stubs |
| `p4maint/fleet/` | Mission 6: state machine, building/updating the fleet state, empty garage (done); status changes, standby swap, garage queue (stubs) | partial |
| `p4maint/eventlog/` | Append-only event log | done |
| `p4maint/dashboard_export/` | Writes the dashboard feed files from a run | done |
| `p4maint/scoring/` | Lead-time metric; the only answer-key reader | done |
| `p4maint/analysis.py` | Missions 1-4 for every robot, once per batch (shared by openloop and pipeline) | done |
| `p4maint/openloop.py` | `make detect`: generator + analysis + scoring before the fleet manager exists | done |
| `p4maint/server.py` | `make dashboard`: serves the repo, plus `/api/scenarios`, `/api/generate`, `/api/job` for the Scenarios panel (local only) | done |
| `p4maint/pipeline.py` | Calls every stage in order (wiring written; helper steps are stubs) | partial |
| `run_scenario.py` | The single demo command | done |
| `dashboard/` | Static HTML/CSS/JS: fleet board, robot detail (plots with limit bands), alert feed, work-order queue | done; runs on fixtures and on generated runs |
| `tests/` | Real: config, contracts, answer-key isolation, generator, ingest, state machine, Missions 1-4, scoring. Stubs: Missions 5-6 | partial |
| `docs/DECISIONS.md` | Every technical decision with sources and open questions | done |
| `docs/FAILURE_MODES.md` | The four faults: signatures, severity, actions | done |

## Not yet implemented

In the order we suggest building them:

Done: the state machine, the whole generator, storage, the event log, Missions 1-4 (`health`, `detect`, `predict`, `diagnose`, combined in `analysis.py`), scoring, and the open-loop runner.

Also done: the dashboard export (`make detect` and `make site-data` feed the dashboard), and the pipeline's `publish` step.

1. `workorders/workorder.py` (Mission 5)
2. `fleet/fleet.py` (`set_robot_status`, `select_standby`, `swap_in_standby`), `fleet/garage.py` (queue, reserve, admit, release), and the pipeline helpers `open_work_order_severities`, `act_on_findings`, `advance_fleet_and_garage` (Mission 6). Then `make demo` runs closed loop end to end and its dashboard shows work orders and the standby swap
3. A multi-fault scenario (two robots failing at once) for the garage queue

Not planned for PDR: CCSDS/XTCE transmit layer, multiple robot types, Missions 7-12, ML.

## Working in parallel (suggested split for four people)

| Person | Owns | Starts from |
|---|---|---|
| A: Generator | `p4maint/generator/`, `tests/test_generator.py` | DECISIONS.md §4 equations, `config/generator.json` |
| B: Detection | `health/`, `detect/`, `tests/test_mission1*`, `test_mission2*` | `fixtures/contracts/telemetry_batch.example.json`, `config/channels.json` |
| C: Prediction & diagnosis | `predict/`, `diagnose/`, `scoring/`, missions 3-4 tests | `fixtures/contracts/prediction.example.json`, FAILURE_MODES.md |
| D: Fleet & dashboard | `fleet/`, `workorders/`, `eventlog/`, `dashboard_export/`, `dashboard/`, missions 5-6 tests | `fixtures/active_work_order/` |

Nobody waits for anyone: each person builds against the fixtures and contracts, and `make validate` / `make test` tell you when your output matches.

## Rules for everyone

- **No hardcoded thresholds.** Every limit, baseline and tuning number comes from `config/` through `p4maint/configs.py`.
- **Never read the answer key** outside `p4maint/scoring`. Never read `config/generator.json` outside `p4maint/generator`. `tests/test_answer_key_isolation.py` enforces both.
- **Validate before you write.** Every JSON file we produce passes `schemas.validate.validate()` first.
- **The event log is append-only.** Never rewrite a line.
- **Plain Python.** Loops and functions over clever one-liners. Ask before adding any dependency beyond pandas, numpy, pyarrow and jsonschema.

## Data formats

Following the HUNCH telemetry briefing's three-layer stack: **Parquet** stores the telemetry record, with columns generated from `config/channels.json`. **JSON** holds config, state objects, work orders and dashboard feeds. Module boundaries follow the **ISO 13374 / OSA-CBM** processing blocks (data acquisition → state detection → health assessment → prognostics → advisory). **CCSDS Space Packets defined with XTCE are not implemented for PDR.** Because the channel table is the single definition of every parameter, an XTCE description can be generated from it and a packet decoder placed in front of ingest later without changing anything downstream. Details: [DECISIONS.md §6](docs/DECISIONS.md#6-schema-file-format).

## Putting this repo on GitHub

The folder is not yet a git repository. From the repo root:

```bash
git init -b main
```

```bash
git add .
```

```bash
git commit -m "PDR skeleton: decisions, contracts, fixtures, stubs, dashboard"
```

Create an **empty** repository on GitHub (github.com → New repository; no README, .gitignore or license, since we already have them), then connect and push. Replace the URL with yours:

```bash
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPO.git
```

```bash
git push -u origin main
```

Then add teammates under the repository's **Settings → Collaborators**. Each teammate runs `git clone <url>`, `cd` into it and `make setup`. To avoid stepping on each other, work on a branch per person (`git switch -c generator`) and merge through pull requests.
