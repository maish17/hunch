"""p4maint - AI predictive maintenance for lunar P2 transport robots.

NASA HUNCH 2026-27, LLASO Project 4 (LLASO-P4-AI-MAINT-2026).

Package map, in the order data flows through it (the HUNCH deck's seven-stage
data journey is in brackets):

    generator/         simulated robot telemetry + answer key   [SENSE, ENCODE]
    ingest/            batches in, Parquet store out            [TRANSMIT, STORE]
    health/            NORMAL / WARNING / CRITICAL per channel  [ANALYZE]       Mission 1
    detect/            anomaly events                           [ANALYZE]       Mission 2
    predict/           trend -> time-to-failure                 [ANALYZE]       Mission 3
    diagnose/          which of the four faults                 [ANALYZE]       Mission 4
    workorders/        work orders for the P5 garage            [DECIDE & ACT]  Mission 5
    fleet/             fleet state, garage queue, standby swap  [UPDATE TWIN, DECIDE & ACT]  Mission 6
    eventlog/          append-only record of every decision
    dashboard_export/  JSON feed files for dashboard/
    scoring/           the ONLY reader of the answer key; measures warning lead time
    pipeline.py        runs all of the above for one scenario (called by run_scenario.py)
"""

__version__ = "0.1.0"
