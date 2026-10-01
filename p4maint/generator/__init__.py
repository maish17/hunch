"""Telemetry generation [SENSE, ENCODE].

Turns a scenario file into simulated P2 telemetry, one 60 s batch at a time, and
writes the answer key. Physics equations E1-E13 are in docs/DECISIONS.md section 4.

    scenario.py      load + check scenario files, make run ids
    physics.py       the equations (E1-E10)
    faults.py        fault progress p(t) and which parameter each fault changes (E13)
    noise.py         seeded random streams, terrain and sensor noise (E11-E12)
    simulate.py      FleetSimulator: steps every robot forward one batch
    ground_truth.py  the answer key (the only file that knows the true failure times)
"""
