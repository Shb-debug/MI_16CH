from __future__ import annotations
import time
from pathlib import Path
from typing import Any
import numpy as np
from models import FBCSPClassifier

class LeftHandDecoder:
    def __init__(self, config: dict[str, Any], model_path: str | Path, sample_rate: float) -> None:
        self.bands = [tuple(b) for b in config["mi_bands"]]
        self.sample_rate = float(sample_rate)
        self.window = float(config.get("window_seconds", 2.0))
        self.step = float(config.get("update_seconds", .15))
        self.high = float(config.get("probability_high", .75))
        self.low = float(config.get("probability_low", .45))
        if not 0.0 < self.low < self.high < 1.0:
            raise ValueError("probability_low must be below probability_high, both in (0, 1)")
        self.confirmations = int(config.get("confirmations", 2))
        self.cooldown = float(config.get("cooldown_seconds", 1.0))
        self.buffers = {b: np.empty((0, int(config.get("channel_count", 16)))) for b in self.bands}
        self.probability = 0.0
        self.state = "BLOCKED"
        self.count = 0
        self.last_event = -1e9
        self.released = True
        self.event_id = 0
        self.next_update = 0.0
        self.model: FBCSPClassifier | None = None
        self.metadata: dict[str, Any] = {}
        if Path(model_path).exists():
            self.model, self.metadata = FBCSPClassifier.load(model_path)
            if abs(float(self.metadata.get("sample_rate", sample_rate)) - sample_rate) > .5:
                raise ValueError("model sample rate does not match LSL sample rate")
            if int(self.metadata.get("channel_count", 16)) != int(config.get("channel_count", 16)):
                raise ValueError("model channel count does not match config")
            self.state = "REST"

    @property
    def model_ready(self) -> bool:
        return self.model is not None

    def add(self, bands: dict[tuple[float, float], np.ndarray], quality: dict[str, Any], timestamp: float) -> tuple[dict[str, Any], bool]:
        if not quality["valid"]:
            self.state, self.count = "BLOCKED", 0
            return self.telemetry(quality, timestamp), False
        for band in self.bands:
            self.buffers[band] = np.vstack((self.buffers[band], bands[band]))[-int(self.sample_rate * 3):]
        needed = int(self.sample_rate * self.window)
        if self.model is None:
            self.state = "NO_MODEL"
            return self.telemetry(quality, timestamp), False
        if min(len(v) for v in self.buffers.values()) < needed or time.monotonic() < self.next_update:
            return self.telemetry(quality, timestamp), False
        self.next_update = time.monotonic() + self.step
        windows = {band: self.buffers[band][-needed:].T for band in self.bands}
        self.probability = .65 * self.probability + .35 * self.model.predict_proba(windows)
        now = time.monotonic()
        if now - self.last_event < self.cooldown:
            self.state, self.count = "COOLDOWN", 0
            return self.telemetry(quality, timestamp), False
        if self.probability > self.high:
            self.count += 1
            self.state = "CANDIDATE"
        elif self.probability <= self.low:
            self.count = 0
            self.state = "REST"
            self.released = True
        event = self.released and self.count >= self.confirmations
        if event:
            self.event_id += 1
            self.last_event, self.count, self.state = now, 0, "COOLDOWN"
            self.released = False
        return self.telemetry(quality, timestamp), event

    def telemetry(self, quality: dict[str, Any], timestamp: float) -> dict[str, Any]:
        return {"type": "mi_telemetry", "target": "left_hand_grasp", "mi_probability": round(self.probability, 4), "state": self.state, "quality_valid": bool(quality["valid"]), "quality_reasons": quality["reasons"], "window_seconds": self.window, "sample_rate": self.sample_rate, "window_end_lsl": timestamp, "model_ready": self.model_ready}
