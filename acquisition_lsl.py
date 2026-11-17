from __future__ import annotations
import time
import uuid
from typing import Any
import numpy as np
from decoder import LeftHandDecoder
from preprocessing import CausalPreprocessor
from quality_control import assess
try:
    import pylsl
except ImportError:
    pylsl = None

def resolve(config: dict[str, Any]):
    if pylsl is None:
        raise RuntimeError("pylsl is not installed")
    streams = list(pylsl.resolve_streams(wait_time=float(config.get("lsl_timeout", 5))))
    name, source, kind = config.get("lsl_stream_name", ""), config.get("lsl_source_id", ""), config.get("lsl_stream_type", "EEG")
    candidates = [x for x in streams if (not name or x.name() == name) and (not source or x.source_id() == source) and (name or source or x.type() == kind)]
    if not candidates:
        raise RuntimeError("no matching LSL EEG stream")
    info = candidates[0]
    indices = config["channel_indices"]
    if info.channel_count() <= max(indices):
        raise RuntimeError("LSL channel count is insufficient")
    rate = float(info.nominal_srate())
    inlet = pylsl.StreamInlet(info, max_buflen=int(config.get("lsl_buffer_seconds", 2)), max_chunklen=16, recover=True)
    return inlet, str(info.name()), rate

def collect_seconds(inlet: Any, seconds: float, indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
    samples, timestamps = [], []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        chunk, ts = inlet.pull_chunk(timeout=.05, max_samples=32)
        if chunk:
            samples.extend(np.asarray(chunk, dtype=np.float64)[:, indices])
            timestamps.extend(ts)
    return np.asarray(samples), np.asarray(timestamps)

class LSLAcquisition:
    def __init__(self, config: dict[str, Any], publish: Any) -> None:
        self.config = config
        self.publish = publish
        self.running = True

    def run(self) -> None:
        try:
            inlet, name, rate = resolve(self.config)
            print("[LSL] connected name=%s rate=%.2f channels=%d" % (name, rate, inlet.info().channel_count()), flush=True)
            preprocessor = CausalPreprocessor(rate, int(self.config["channel_count"]), self.config)
            decoder = LeftHandDecoder(self.config, self.config.get("model_path", "artifacts/mi_model.joblib"), rate)
            session_id = uuid.uuid4().hex[:10]
            self.publish({"type": "status", "mode": "real", "lsl_connected": True, "model_ready": decoder.model_ready, "sample_rate": rate, "stream_name": name, "message": "LSL EEG 已连接"})
            while self.running:
                chunk, timestamps = inlet.pull_chunk(timeout=.2, max_samples=32)
                if not chunk:
                    continue
                raw = np.asarray(chunk, dtype=np.float64)[:, self.config["channel_indices"]]
                quality = assess(raw, self.config)
                bands = preprocessor.process(raw)
                end_ts = float(timestamps[-1]) if timestamps else 0.0
                telemetry, event = decoder.add(bands, quality, end_ts)
                telemetry.update({"mode": "real", "simulated": False, "stream_name": name})
                self.publish(telemetry)
                if event:
                    self.publish({"type": "mi_event", "event_id": f"{session_id}-{decoder.event_id}", "command": "LEFT_HAND_GRASP", "confidence": decoder.probability, "mode": "real", "simulated": False, "timestamp": end_ts})
        except Exception as exc:
            print("[LSL_ERROR] %s" % exc, flush=True)
            self.publish({"type": "status", "mode": "real", "lsl_connected": False, "model_ready": False, "state": "ERROR", "message": str(exc)})
