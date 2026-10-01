"""Ingest and storage. STUBS: remove @skip as p4maint/ingest is built."""

import unittest

TODO = unittest.skip("TODO(ingest): needs p4maint.ingest")


class TestStore(unittest.TestCase):
    @TODO
    def test_parquet_round_trip(self):
        """Write three batches, close, read back: same rows, dtypes from config/channels.json."""

    @TODO
    def test_batch_json_round_trip(self):
        """batch_to_json -> validates as telemetry_batch -> json_to_frame gives the same data;
        NaN dropouts become null and back."""

    @TODO
    def test_bad_batch_rejected(self):
        """check_batch reports a missing channel, a duplicate t_s and an unknown op_mode."""

    @TODO
    def test_rolling_window_trims_old_rows(self):
        """RollingWindow(1800) keeps only the last 1800 s per robot."""


if __name__ == "__main__":
    unittest.main()
