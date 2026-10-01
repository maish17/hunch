# Fixtures

Hand-made example files for every JSON contract in `schemas/`. They exist so the dashboard and every backend module can be built and tested **today**, before the generator or pipeline work. Every file here validates (`make validate`), and `tests/test_contracts.py` keeps it that way.

## What's here

| Folder | Contents | Use it for |
|---|---|---|
| `healthy_fleet/` | Complete dashboard feed set at T+01:30. Three robots on missions, two on standby, everything NORMAL, no alerts, empty garage | Empty states and the all-green board |
| `active_work_order/` | Complete dashboard feed set at T+03:10 with an active work order and a dispatched standby (story below), plus `events.jsonl` (the decision record), `fleet_state.json` and `garage_queue.json` | Every view with real content |
| `contracts/` | One standalone example per contract: telemetry batch, health snapshot, anomaly event, prediction, work order, fleet state, garage queue, event log, answer key | Reading the contracts; unit-test inputs |

Each feed folder has the same files a real run writes to `runs/<run_id>/dashboard/`: `feed_index.json`, `fleet_board.json`, `robot_P2-0N.json` (×5), `alerts.json` and `work_orders.json`. The dashboard opens `active_work_order` by default. Switch with the "Data" menu, or pass `?feed=../fixtures/healthy_fleet/feed_index.json`.

## The `active_work_order` story

Same fleet and missions as `scenarios/bearing_wear_p2_02.json`. Hub bearing wear starts on P2-02's front-left wheel at T+01:00 and truly fails at T+03:30. A second, made-up fault (battery degradation on P2-03, from T+01:06:40) was added so the queue view has something waiting.

| Time (t_s) | Event |
|---|---|
| 10500 | PR-000001: P2-02 trend predicts bearing failure in 56 min (true remaining: 35 min; a straight line underestimates the accelerating wear). Severity CRITICAL. |
| 10560 | WO-20270301-0001 created. P2-02 → MAINTENANCE_REQUIRED. P2-04 picked over P2-05 (higher SOC) and takes over M-HAUL-B. BAY-1 reserved. P2-02 → EN_ROUTE_P5. |
| 10620 | P2-02 front-left temperature passes baseline + 15 °C (anomaly AN-000001, detected 10680). The prediction came **before** the threshold crossing, which is the point of Mission 3. |
| 10800 | P2-03 voltage sags more than 0.5 V under load (AN-000002, detected 10860) |
| 10920 | PR-000002: P2-03 battery degradation, WARNING |
| 10980 | WO-20270301-0002 queued at position 1. BAY-1 is taken, and as a WARNING P2-03 keeps working. |
| **11400** | **Snapshot time.** P2-02 arrives at P5 at 11460. |

At the snapshot, P2-02's front-left drive is +19 °C over baseline (THERMAL WARNING) while its current (+0.9 A) and speed (−0.06 rad/s) are still NORMAL: the multi-channel bearing-wear pattern, caught early.

## How they were made

The time series were produced by a throwaway authoring script with simple shapes: per-mode baselines from `config/modes.json`, a first-order lag for temperatures, hand-shaped fault ramps and small random noise. That script is **not** the generator and is deliberately not in the repo. Treat these files as hand-written data.

## Rules

- If you change a schema, update the fixtures in the same commit and run `make validate`.
- Don't make the dashboard depend on anything that is not in these files. If the page needs a new field, add it to the schema and the fixtures first, then ask the backend owner to produce it.
- Values are plausible, not authoritative. The real numbers come from runs.
