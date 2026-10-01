"""Parquet telemetry store and JSON telemetry batches.

Responsibility: check each incoming batch, append it to runs/<run_id>/telemetry.parquet
(one row group per batch, via pyarrow.parquet.ParquetWriter), read slices back, and
convert to/from the JSON telemetry_batch contract.

Column layout comes ONLY from config/channels.json: record_fields (robot_id, t_s,
timestamp, op_mode) then every channel with its dtype. Because the layout is
table-driven, a future CCSDS Space Packet / XTCE layer can be generated from the
same table: XTCE parameters = channel rows, packet = one sample. Nothing here needs
to change when that layer is added in front of ingest.

STATUS: stubs.
"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def arrow_schema(channels_cfg: dict) -> pa.Schema:
    """Arrow schema built from config/channels.json.

    TODO(ingest owner): robot_id -> pa.string(), t_s -> pa.int64(),
    timestamp -> pa.timestamp("ms", tz="UTC"), op_mode -> pa.dictionary(pa.int8(), pa.string()),
    each channel -> pa.float32() (its dtype). Attach units/labels as field metadata.
    """
    raise NotImplementedError("arrow_schema")


def check_batch(df: pd.DataFrame, channels_cfg: dict) -> list[str]:
    """Problems with a batch before it is stored (empty list = fine).

    TODO(ingest owner): missing/extra columns, wrong column order, t_s not strictly
    increasing per robot, duplicate (robot_id, t_s), op_mode not in config/modes.json.
    Missing sensor values (NaN) are allowed - they are dropouts, not errors.
    """
    raise NotImplementedError("check_batch")


def open_store(path: Path, channels_cfg: dict) -> pq.ParquetWriter:
    """Create the Parquet file for a run and return a writer."""
    raise NotImplementedError("open_store")


def append_batch(writer: pq.ParquetWriter, df: pd.DataFrame, channels_cfg: dict) -> None:
    """Append one batch (all robots, 60 s) as one row group."""
    raise NotImplementedError("append_batch")


def close_store(writer: pq.ParquetWriter) -> None:
    """Finish the Parquet file. It cannot be read until this is called."""
    raise NotImplementedError("close_store")


def read_telemetry(path: Path, robot_id: str | None = None, start_t_s: int | None = None,
                   end_t_s: int | None = None, channels: list[str] | None = None) -> pd.DataFrame:
    """Read a slice of a finished run (used by scoring, dashboard export, notebooks)."""
    raise NotImplementedError("read_telemetry")


def batch_to_json(df: pd.DataFrame, robot_id: str, batch_seq: int, channels_cfg: dict) -> dict:
    """One robot's rows -> telemetry_batch contract dict (NaN becomes null)."""
    raise NotImplementedError("batch_to_json")


def json_to_frame(batch: dict) -> pd.DataFrame:
    """telemetry_batch contract dict -> DataFrame with the standard columns."""
    raise NotImplementedError("json_to_frame")
