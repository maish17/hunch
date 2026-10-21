"""Ingest and storage: Parquet store, telemetry-batch JSON, rolling window, event log."""

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from p4maint import configs
from p4maint.eventlog.log import EventLog
from p4maint.generator.scenario import load_scenario
from p4maint.generator.simulate import FleetSimulator, open_loop_fleet_state
from p4maint.ingest.history import RollingWindow
from p4maint.ingest.store import (append_batch, batch_to_json, check_batch, close_store, json_to_frame,
                                  open_store, read_telemetry)
from p4maint.paths import SCENARIOS_DIR
from schemas.validate import ContractError, validate

CHANNELS = configs.load_channels()


def three_batches() -> list[pd.DataFrame]:
    scenario = load_scenario(SCENARIOS_DIR / "healthy_baseline.json")
    sim = FleetSimulator(scenario, configs.load_generator_params(), configs.load_modes(), configs.load_faults(),
                         CHANNELS, configs.load_state_machine())
    fleet = open_loop_fleet_state(scenario)
    return [sim.step(fleet, {}) for _ in range(3)]


class TestStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batches = three_batches()

    def test_parquet_round_trip(self):
        """Write three batches, close, read back: same rows, dtypes from config/channels.json."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "telemetry.parquet"
            writer = open_store(path, CHANNELS)
            for batch in self.batches:
                append_batch(writer, batch, CHANNELS)
            close_store(writer)
            back = read_telemetry(path)
            only_p2_01 = read_telemetry(path, robot_id="P2-01", start_t_s=60, end_t_s=119, channels=["wheel_fl_current_a"])
        original = pd.concat(self.batches, ignore_index=True)
        self.assertEqual(len(back), len(original))
        self.assertEqual(list(back.columns), list(original.columns))
        self.assertEqual(back["wheel_fl_temp_c"].dtype, np.float32)
        np.testing.assert_array_equal(back["battery_voltage_v"].to_numpy(), original["battery_voltage_v"].to_numpy())
        self.assertEqual(len(only_p2_01), 60)
        self.assertEqual(list(only_p2_01.columns), ["robot_id", "t_s", "timestamp", "op_mode", "wheel_fl_current_a"])

    def test_batch_json_round_trip(self):
        """batch_to_json -> validates as telemetry_batch -> json_to_frame gives the same data;
        NaN dropouts become null and back."""
        batch = self.batches[0].copy()
        batch.loc[batch.index[5], "wheel_rr_speed_rads"] = np.nan
        as_json = batch_to_json(batch, "P2-01", 0, CHANNELS)
        validate(as_json, "telemetry_batch")
        self.assertEqual(len(as_json["samples"]), 60)
        self.assertIsNone(as_json["samples"][5]["wheel_rr_speed_rads"])
        back = json_to_frame(as_json)
        original = batch[batch["robot_id"] == "P2-01"].reset_index(drop=True)
        self.assertTrue(math.isnan(back.loc[5, "wheel_rr_speed_rads"]))
        np.testing.assert_allclose(back["wheel_fl_temp_c"], original["wheel_fl_temp_c"], atol=1e-3)

    def test_good_batch_passes(self):
        self.assertEqual(check_batch(self.batches[0], CHANNELS), [])

    def test_bad_batch_rejected(self):
        """check_batch reports a missing channel, a duplicate t_s and an unknown op_mode."""
        self.assertTrue(check_batch(self.batches[0].drop(columns=["battery_soc_pct"]), CHANNELS))
        duplicated = pd.concat([self.batches[0], self.batches[0].head(1)], ignore_index=True)
        self.assertIn("duplicate (robot_id, t_s) rows", check_batch(duplicated, CHANNELS))
        bad_mode = self.batches[0].copy()
        bad_mode.loc[bad_mode.index[0], "op_mode"] = "DANCING"
        self.assertIn("unknown op_mode values: ['DANCING']", check_batch(bad_mode, CHANNELS))

    def test_rolling_window_trims_old_rows(self):
        """RollingWindow keeps only the last max_window_s seconds per robot."""
        window = RollingWindow(90)
        for batch in self.batches:
            window.add(batch)
        rows = window.window("P2-01", 1000)
        self.assertEqual(rows["t_s"].min(), 180 - 90)
        self.assertEqual(rows["t_s"].max(), 179)
        self.assertEqual(len(window.window("P2-01", 30)), 30)
        self.assertTrue(window.window("NOPE", 30).empty)


class TestEventLog(unittest.TestCase):
    def test_append_only_and_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp) / "events.jsonl", "2027-03-01T00:00:00Z")
            first = log.append("RUN_STARTED", 0, None, "Run started", {"scenario_id": "x"})
            second = log.append("ROBOT_STATUS_CHANGED", 75, "P2-02", "P2-02 ACTIVE -> MAINTENANCE_REQUIRED",
                                {"from": "ACTIVE", "to": "MAINTENANCE_REQUIRED"}, {"caused_by_event_id": first["event_id"]})
            self.assertEqual(second["event_id"], "EV-000002")
            self.assertEqual(second["at"], "2027-03-01T00:01:15Z")
            reopened = EventLog(Path(tmp) / "events.jsonl", "2027-03-01T00:00:00Z")
            self.assertEqual(reopened.next_number, 3)
            self.assertEqual([e["event_id"] for e in reopened.read_all()], ["EV-000001", "EV-000002"])
            with self.assertRaises(ContractError):
                log.append("NOT_A_TYPE", 0, None, "bad", {})
            self.assertEqual(len(log.read_all()), 2)


if __name__ == "__main__":
    unittest.main()
