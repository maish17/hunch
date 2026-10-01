"""Schema and config loading.

Responsibility: read the files in config/ and hand them to the rest of the code as
plain dicts. This is the ONLY way code should get a limit, baseline, physical
constant or tuning value - nothing anywhere may hardcode a threshold.

Which code may read which file:
    channels.json, modes.json, detector.json   - health, detect, predict, diagnose
    faults.json                                - generator and diagnose (signatures)
    generator.json                             - generator ONLY (world truth)
    state_machine.json, dispatch.json          - fleet, workorders

These loaders are plumbing (no algorithms), so they are implemented.
"""

import json
from pathlib import Path

from p4maint.paths import CONFIG_DIR


def load_json(path: Path) -> dict:
    """Read one JSON file and return it as a dict."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config(name: str) -> dict:
    """Load config/<name>.json, e.g. load_config("channels")."""
    return load_json(CONFIG_DIR / f"{name}.json")


def load_channels() -> dict:
    return load_config("channels")


def load_modes() -> dict:
    return load_config("modes")


def load_faults() -> dict:
    return load_config("faults")


def load_detector_params() -> dict:
    return load_config("detector")


def load_generator_params() -> dict:
    """World-truth physics. Generator only - see module docstring."""
    return load_config("generator")


def load_state_machine() -> dict:
    return load_config("state_machine")


def load_dispatch() -> dict:
    return load_config("dispatch")


def channel_names(channels_cfg: dict) -> list[str]:
    """All measured channel names, in config order (this is also the column order)."""
    return [channel["name"] for channel in channels_cfg["channels"]]


def get_channel(channels_cfg: dict, name: str) -> dict:
    """The full definition of one channel. Raises KeyError for an unknown name."""
    for channel in channels_cfg["channels"]:
        if channel["name"] == name:
            return channel
    raise KeyError(f"Unknown channel '{name}' - is it in config/channels.json?")


def get_mode(modes_cfg: dict, mode_id: str) -> dict:
    """The full definition of one operating mode. Raises KeyError for an unknown id."""
    for mode in modes_cfg["modes"]:
        if mode["id"] == mode_id:
            return mode
    raise KeyError(f"Unknown operating mode '{mode_id}' - is it in config/modes.json?")


def get_fault(faults_cfg: dict, fault_id: str) -> dict:
    """The full definition of one fault type. Raises KeyError for an unknown id."""
    for fault in faults_cfg["faults"]:
        if fault["id"] == fault_id:
            return fault
    raise KeyError(f"Unknown fault type '{fault_id}' - is it in config/faults.json?")
