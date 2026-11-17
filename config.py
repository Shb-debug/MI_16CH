from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_BANDS = ((4.0, 8.0), (8.0, 12.0), (12.0, 16.0), (16.0, 20.0), (20.0, 24.0), (24.0, 30.0), (30.0, 40.0))

def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data["config_path"] = str(config_path.resolve())
    data["channel_indices"] = [int(v) for v in data["channel_indices"]]
    data["mi_bands"] = [tuple(float(v) for v in band) for band in data.get("mi_bands", DEFAULT_BANDS)]
    if len(data["channel_indices"]) != int(data.get("channel_count", 16)):
        raise ValueError("channel_indices length must equal channel_count")
    if len(set(data["channel_indices"])) != len(data["channel_indices"]):
        raise ValueError("channel_indices contains duplicates")
    for low, high in data["mi_bands"]:
        if not 0 < low < high:
            raise ValueError("invalid MI frequency band")
    return data
