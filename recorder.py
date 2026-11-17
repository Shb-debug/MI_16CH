from __future__ import annotations
from pathlib import Path
import numpy as np

def save_trials(path: str | Path, epochs: list[np.ndarray], labels: list[int], timestamps: list[float], sample_rate: float, channel_order: list[str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, X=np.asarray(epochs, dtype=np.float64), y=np.asarray(labels, dtype=np.int64), timestamps=np.asarray(timestamps, dtype=np.float64), sample_rate=float(sample_rate), channel_order=np.asarray(channel_order))
