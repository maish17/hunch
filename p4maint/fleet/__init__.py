"""Fleet and garage state [UPDATE DIGITAL TWIN, DECIDE & ACT] - Mission 6 (Send in the Backup).

    state_machine.py   legal robot and work-order transitions; rejects illegal ones
    fleet.py           fleet_state contract: statuses, missions, standby selection and swap
    garage.py          garage_queue contract: P5 bays and the priority queue

This package never looks at telemetry. It only sees health scores/statuses,
predictions and work orders, so fleet logic and detection logic stay separable.
"""
