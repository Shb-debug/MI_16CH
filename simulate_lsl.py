"""Publish safe synthetic 16-channel EEG-like data through LSL."""

from __future__ import annotations

import argparse
import time

import numpy as np
import pylsl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="mi_simulated_eeg")
    parser.add_argument("--source-id", default="mi_simulator")
    parser.add_argument("--rate", type=float, default=250.0)
    parser.add_argument("--channels", type=int, default=16)
    args = parser.parse_args()

    info = pylsl.StreamInfo(args.name, "EEG", args.channels, args.rate, "float32", args.source_id)
    outlet = pylsl.StreamOutlet(info, chunk_size=25, max_buffered=10)
    rng = np.random.default_rng(17)
    phase = 0.0
    step = 25 / args.rate
    print(f"[LSL-SIM] name={args.name} source_id={args.source_id} channels={args.channels} rate={args.rate}", flush=True)
    try:
        while True:
            t = phase + np.arange(25) / args.rate
            signal = 0.00025 * rng.standard_normal((25, args.channels))
            signal += 0.00015 * np.sin(2 * np.pi * 10 * t)[:, None]
            signal += 0.00010 * np.sin(2 * np.pi * 20 * t)[:, None]
            outlet.push_chunk(signal.astype(np.float32).tolist())
            phase += step
            time.sleep(step)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
