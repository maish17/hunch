"""Parquet telemetry store and JSON telemetry batches.

Responsibility: check each incoming batch, append it to runs/<run_id>/telemetry.parquet
(one row group per batch, via pyarrow.parquet.ParquetWriter), read slices back, and
convert to/from the JSON telemetry_batch contract.

Column layout comes ONLY from config/channels.json: record_fields (robot_id, t_s,
timestamp, op_mode) then every channel with its dtype. Because the layout is
table-driven, a future CCSDS Space Packet / XTCE layer can be generated from the
same table: XTCE parameters = channel rows, packet = one sample. Nothing here needs
to change when that layer is added in front of ingest.
"""

import math
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from p4maint.configs import channel_names, load_modes

RECORD_COLUMNS = ["robot_id", "t_s", "timestamp", "op_mode"]
ARROW_TYPES = {"float32": pa.float32(), "float64": pa.float64(), "int32": pa.int32(), "int64": pa.int64()}


def arrow_schema(channels_cfg: dict) -> pa.Schema:
    """Arrow schema built from config/channels.json.

    robot_id and op_mode are strings (Parquet dictionary-encodes them on disk anyway),
    t_s is int64, timestamp is milliseconds UTC, each channel uses its configured dtype.
    Units and labels are stored as field metadata so the file describes itself.
    """
    fields = [
        pa.field("robot_id", pa.string()),
        pa.field("t_s", pa.int64()),
        pa.field("timestamp", pa.timestamp("ms", tz="UTC")),
        pa.field("op_mode", pa.string()),
    ]
    for channel in channels_cfg["channels"]:
        metadata = {"units": channel["units"], "label": channel["label"]}
        fields.append(pa.field(channel["name"], ARROW_TYPES[channel["dtype"]], metadata=metadata))
    return pa.schema(fields)


def check_batch(df: pd.DataFrame, channels_cfg: dict, modes_cfg: dict | None = None) -> list[str]:
    """Problems with a batch before it is stored (empty list = fine).

    Checks: exact column set and order, t_s strictly increasing per robot, no duplicate
    (robot_id, t_s), op_mode is a known mode. Missing sensor values (NaN) are allowed -
    they are dropouts, not errors.
    """
    problems = []
    expected = RECORD_COLUMNS + channel_names(channels_cfg)
    if list(df.columns) != expected:
        missing = [c for c in expected if c not in df.columns]
        extra = [c for c in df.columns if c not in expected]
        if missing:
            problems.append(f"missing columns: {missing}")
        if extra:
            problems.append(f"unexpected columns: {extra}")
        if not missing and not extra:
            problems.append("columns are not in config/channels.json order")
        return problems

    if df.duplicated(subset=["robot_id", "t_s"]).any():
        problems.append("duplicate (robot_id, t_s) rows")
    for robot_id, rows in df.groupby("robot_id"):
        if not rows["t_s"].is_monotonic_increasing:
            problems.append(f"t_s is not increasing for {robot_id}")

    modes_cfg = modes_cfg or load_modes()
    known_modes = {mode["id"] for mode in modes_cfg["modes"]}
    unknown = set(df["op_mode"].unique()) - known_modes
    if unknown:
        problems.append(f"unknown op_mode values: {sorted(unknown)}")
    return problems


def _to_table(df: pd.DataFrame, channels_cfg: dict) -> pa.Table:
    schema = arrow_schema(channels_cfg)
    df = df.copy()
    for channel in channels_cfg["channels"]:
        df[channel["name"]] = df[channel["name"]].astype(channel["dtype"])
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False)


def open_store(path: Path, channels_cfg: dict) -> pq.ParquetWriter:
    """Create the Parquet file for a run and return a writer."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return pq.ParquetWriter(str(path), arrow_schema(channels_cfg))


def append_batch(writer: pq.ParquetWriter, df: pd.DataFrame, channels_cfg: dict) -> None:
    """Append one batch (all robots, 60 s) as one row group."""
    writer.write_table(_to_table(df, channels_cfg))


def close_store(writer: pq.ParquetWriter) -> None:
    """Finish the Parquet file. It cannot be read until this is called."""
    writer.close()


def read_telemetry(path: Path, robot_id: str | None = None, start_t_s: int | None = None,
                   end_t_s: int | None = None, channels: list[str] | None = None) -> pd.DataFrame:
    """Read a slice of a finished run (used by scoring, dashboard export, notebooks).

    start_t_s and end_t_s are inclusive. channels limits which channel columns are read;
    the record columns are always included.
    """
    filters = []
    if robot_id is not None:
        filters.append(("robot_id", "==", robot_id))
    if start_t_s is not None:
        filters.append(("t_s", ">=", start_t_s))
    if end_t_s is not None:
        filters.append(("t_s", "<=", end_t_s))
    columns = None if channels is None else RECORD_COLUMNS + list(channels)
    table = pq.read_table(str(path), columns=columns, filters=filters or None)
    return table.to_pandas()


def batch_to_json(df: pd.DataFrame, robot_id: str, batch_seq: int, channels_cfg: dict) -> dict:
    """One robot's rows -> telemetry_batch contract dict (NaN becomes null)."""
    names = channel_names(channels_cfg)
    rows = df[df["robot_id"] == robot_id].sort_values("t_s")
    samples = []
    for _, row in rows.iterrows():
        sample = {
            "t_s": int(row["t_s"]),
            "timestamp": pd.Timestamp(row["timestamp"]).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "op_mode": row["op_mode"],
        }
        for name in names:
            value = float(row[name])
            sample[name] = None if math.isnan(value) else round(value, 4)
        samples.append(sample)
    t_values = rows["t_s"]
    sample_rate = 1.0 if len(rows) < 2 else (len(rows) - 1) / float(t_values.iloc[-1] - t_values.iloc[0])
    return {
        "schema_version": "1.0.0",
        "robot_id": robot_id,
        "robot_type": "P2_TRANSPORT",
        "batch_seq": batch_seq,
        "sample_rate_hz": sample_rate,
        "start_t_s": int(t_values.iloc[0]),
        "end_t_s": int(t_values.iloc[-1]),
        "channels": names,
        "samples": samples,
    }


def json_to_frame(batch: dict) -> pd.DataFrame:
    """telemetry_batch contract dict -> DataFrame with the standard columns."""
    df = pd.DataFrame(batch["samples"])
    df.insert(0, "robot_id", batch["robot_id"])
    df["t_s"] = df["t_s"].astype("int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for name in batch["channels"]:
        df[name] = pd.to_numeric(df[name], errors="coerce").astype("float32")
    return df[RECORD_COLUMNS + batch["channels"]]
