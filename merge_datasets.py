from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np

def load(path: Path):
    data = np.load(path)
    required = {"X", "y", "timestamps", "sample_rate", "channel_order"}
    missing = required.difference(data.files)
    if missing:
        raise ValueError("%s missing fields: %s" % (path, sorted(missing)))
    return data

def main() -> None:
    parser = argparse.ArgumentParser(description="Merge compatible MI trial datasets")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/merged_left_hand.npz"))
    args = parser.parse_args()
    datasets = [load(path) for path in args.inputs]
    first = datasets[0]
    rate = float(np.asarray(first["sample_rate"]).item())
    order = np.asarray(first["channel_order"]).astype(str)
    shape = np.asarray(first["X"]).shape[1:]
    for path, data in zip(args.inputs, datasets):
        x, y = np.asarray(data["X"]), np.asarray(data["y"]).astype(np.int64).ravel()
        current_rate = float(np.asarray(data["sample_rate"]).item())
        current_order = np.asarray(data["channel_order"]).astype(str)
        if x.ndim != 3 or x.shape[1:] != shape:
            raise ValueError("%s has incompatible X shape %s, expected (*,%s)" % (path, x.shape, shape))
        if len(x) != len(y):
            raise ValueError("%s has different X/y lengths" % path)
        if abs(current_rate - rate) > .01 or not np.array_equal(current_order, order):
            raise ValueError("%s has incompatible sample rate or channel order" % path)
    x = np.concatenate([np.asarray(d["X"]) for d in datasets], axis=0)
    y = np.concatenate([np.asarray(d["y"]).astype(np.int64).ravel() for d in datasets])
    ts = np.concatenate([np.asarray(d["timestamps"], dtype=np.float64).ravel() for d in datasets])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, X=x, y=y, timestamps=ts, sample_rate=rate, channel_order=order)
    print("[MERGED]", args.output, "epochs=", len(y), "labels=", dict(zip(*np.unique(y, return_counts=True))))

if __name__ == "__main__":
    main()
