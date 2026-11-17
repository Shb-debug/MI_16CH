from __future__ import annotations

from typing import Any
import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, tf2sos, sosfiltfilt

class CausalPreprocessor:
    """Unit conversion, CAR, notch and stateful causal filter bank."""
    def __init__(self, sample_rate: float, channels: int, config: dict[str, Any]) -> None:
        self.sample_rate = float(sample_rate)
        self.channels = int(channels)
        self.scale = float(config.get("signal_scale", 1.0))
        self.reference = str(config.get("reference", "CAR")).upper()
        self.bands = tuple(tuple(float(v) for v in b) for b in config["mi_bands"])
        self.notch_sos = None
        self.notch_state = None
        notch_hz = float(config.get("notch_hz", 50.0))
        if 0 < notch_hz < self.sample_rate / 2:
            b, a = iirnotch(notch_hz, float(config.get("notch_q", 30.0)), fs=self.sample_rate)
            self.notch_sos = tf2sos(b, a)
            self.notch_state = np.zeros((len(self.notch_sos), 2, channels))
        self.sos = {band: butter(4, band, btype="bandpass", fs=self.sample_rate, output="sos") for band in self.bands}
        self.states = {band: np.zeros((len(self.sos[band]), 2, channels)) for band in self.bands}

    def prepare(self, samples: np.ndarray) -> np.ndarray:
        values = np.asarray(samples, dtype=np.float64).copy() * self.scale
        if values.ndim != 2 or values.shape[1] != self.channels:
            raise ValueError("expected samples with shape (n, %d)" % self.channels)
        values -= np.median(values, axis=0, keepdims=True)
        if self.reference == "CAR":
            values -= np.mean(values, axis=1, keepdims=True)
        if self.notch_sos is not None and self.notch_state is not None:
            values, self.notch_state = sosfilt(self.notch_sos, values, axis=0, zi=self.notch_state)
        return values

    def process(self, samples: np.ndarray) -> dict[tuple[float, float], np.ndarray]:
        values = self.prepare(samples)
        output = {}
        for band, sos in self.sos.items():
            filtered, self.states[band] = sosfilt(sos, values, axis=0, zi=self.states[band])
            output[band] = filtered
        return output

def offline_filter_epochs(epochs: np.ndarray, sample_rate: float, config: dict[str, Any]) -> dict[tuple[float, float], np.ndarray]:
    values = np.asarray(epochs, dtype=np.float64) * float(config.get("signal_scale", 1.0))
    values -= np.median(values, axis=2, keepdims=True)
    if str(config.get("reference", "CAR")).upper() == "CAR":
        values -= np.mean(values, axis=1, keepdims=True)
    output = {}
    for band in config["mi_bands"]:
        band = tuple(float(v) for v in band)
        sos = butter(4, band, btype="bandpass", fs=sample_rate, output="sos")
        output[band] = np.asarray([sosfiltfilt(sos, epoch, axis=1) for epoch in values])
    return output
