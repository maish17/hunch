# P4 Predictive Maintenance: lunar robot fleet health

NASA HUNCH 2026-27 SFT · LLASO Project 4 (`LLASO-P4-AI-MAINT-2026`)

An AI system that reads lunar transport-robot telemetry, flags problems, predicts failures before they happen, writes work orders for the P5 Repair Garage and puts a standby robot into service, without a human watching. PDR scope is **Missions 1-6** for the **P2 transport robot**, using **rule-based thresholds plus trend extrapolation** (no machine learning).

> **Status: skeleton.** The decisions, data contracts, fixtures, dashboard and test plan are in place. Detection, prediction and diagnosis logic are **stubs for the team to write**. Running a scenario stops at the first unbuilt stage and names it. That message is our progress meter.

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

Then open http://localhost:8000/dashboard/. The dashboard runs on the fixtures right now.

```bash
make demo
```

This runs `scenarios/bearing_wear_p2_02.json` end to end. Today it stops at `build_ground_truth`, the first stub.

| Command | What it does |
|---|---|
| `make setup` | Create `.venv` and install pandas, numpy, pyarrow, jsonschema |
| `make validate` | Check config, scenarios and every fixture against `schemas/` |
| `make test` | 29 real tests pass now; 79 mission/stage stubs show as *skipped* until built |
| `make demo` / `make healthy` | Run the bearing-wear / healthy scenario: `python run_scenario.py <scenario>` |
| `make dashboard` | Serve the repo at http://localhost:8000/dashboard/ |
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
| `scenarios/` | `healthy_baseline.json`, `bearing_wear_p2_02.json` | done |
| `p4maint/configs.py`, `p4maint/paths.py` | Config loading, file locations | done |
| `p4maint/generator/` | Scenario loading (done), physics, faults, noise, simulator, answer key | stubs |
| `p4maint/ingest/` | Parquet store, telemetry batches, rolling window | stubs |
| `p4maint/health/` | Mission 1: status per channel vs mode baseline, roll-up | stubs |
| `p4maint/detect/` | Mission 2: debounced anomaly events | stubs |
| `p4maint/predict/` | Mission 3: trend fit, time-to-failure, prediction contract | stubs |
| `p4maint/diagnose/` | Mission 4: residuals, signature matching | stubs |
| `p4maint/workorders/` | Mission 5: work orders | stubs |
| `p4maint/fleet/` | Mission 6: state machine, fleet state, garage queue, standby swap | stubs |
| `p4maint/eventlog/` | Append-only event log | stubs |
| `p4maint/dashboard_export/` | Writes the dashboard feed files | stubs |
| `p4maint/scoring/` | Lead-time metric; the only answer-key reader | stubs |
| `p4maint/pipeline.py` | Calls every stage in order (wiring written; helper steps are stubs) | partial |
| `run_scenario.py` | The single demo command | done |
| `dashboard/` | Static HTML/CSS/JS: fleet board, robot detail (plots with limit bands), alert feed, work-order queue | done on fixtures |
| `tests/` | Real: config, contracts, answer-key isolation. Stubs: one file per mission 1-6 plus each stage | partial |
| `docs/DECISIONS.md` | Every technical decision with sources and open questions | done |
| `docs/FAILURE_MODES.md` | The four faults: signatures, severity, actions | done |

## Not yet implemented

In the order we suggest building them:

1. `fleet/state_machine.py`: the transition checks (≈10 lines; a good first task)
2. `generator/physics.py`, `faults.py`, `noise.py`, then `simulate.py` and `ground_truth.py`
3. `ingest/store.py`, `ingest/history.py`, `eventlog/log.py`
4. `health/evaluate.py` (Mission 1)
5. `detect/anomaly.py` (Mission 2)
6. `diagnose/residuals.py`, `diagnose/diagnosis.py` (Mission 4)
7. `predict/trend.py`, `predict/prediction.py` (Mission 3)
8. `workorders/workorder.py` (Mission 5)
9. `fleet/fleet.py`, `fleet/garage.py`, and the pipeline helpers `analyse_robot`, `advance_fleet_and_garage`, `publish` (Mission 6)
10. `dashboard_export/feeds.py`: real runs produce the same files as the fixtures
11. `scoring/lead_time.py`: the headline metric
12. `generator/scenario.py check_scenario_references`

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
