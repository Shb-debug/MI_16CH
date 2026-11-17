from __future__ import annotations
from typing import Any
import numpy as np

def assess(samples: np.ndarray, config: dict[str, Any]) -> dict[str, Any]:
    values = np.asarray(samples, dtype=np.float64)
    reasons: list[str] = []
    expected = int(config.get("channel_count", 16))
    if values.ndim != 2 or values.shape[1] != expected:
        reasons.append("channel_shape")
    if not np.isfinite(values).all():
        reasons.append("nan_or_inf")
    peak = 0.0
    if values.size:
        peak = float(np.percentile(np.abs(values - np.median(values, axis=0)), 99.5))
        variance = np.var(values, axis=0)
        if peak > float(config.get("quality_peak_limit", 5000.0)):
            reasons.append("amplitude_saturation")
        if np.any(variance < float(config.get("quality_flatline_variance", 1e-8))):
            reasons.append("flatline")
    return {"valid": not reasons, "reasons": reasons, "peak": peak}
