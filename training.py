from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
import numpy as np
from sklearn.model_selection import train_test_split
from acquisition_lsl import resolve, collect_seconds
from config import load_config
from preprocessing import offline_filter_epochs
from models import FBCSPClassifier
from protocol import announce, trial_order
from recorder import save_trials

def collect(config: dict, output: Path, trials_per_class: int) -> None:
    inlet, name, rate = resolve(config)
    print("[LSL] %s channels=%d sample_rate=%.2f" % (name, inlet.info().channel_count(), rate))
    epochs, labels, timestamps = [], [], []
    for number, label in enumerate(trial_order(trials_per_class), 1):
        input("Press Enter to start trial %d/%d..." % (number, trials_per_class * 2))
        announce(0, 2.0)
        collect_seconds(inlet, 2.0, config["channel_indices"])
        announce(label, 4.0)
        samples, ts = collect_seconds(inlet, 4.0, config["channel_indices"])
        required = int(round(rate * 2.0))
        if len(samples) >= required:
            epochs.append(samples[-required:].T)
            labels.append(label)
            timestamps.append(float(ts[-1]) if len(ts) else 0.0)
    save_trials(output, epochs, labels, timestamps, rate, config["channel_order"])
    print("[COLLECTED]", output, "epochs=", len(epochs))

def train(config: dict, data_path: Path, model_path: Path) -> None:
    data = np.load(data_path)
    X, y = np.asarray(data["X"]), np.asarray(data["y"]).astype(int)
    rate = float(np.asarray(data["sample_rate"]).item())
    train_idx, test_idx = train_test_split(np.arange(len(y)), test_size=.25, stratify=y, random_state=17)
    bands = offline_filter_epochs(X, rate, config)
    model = FBCSPClassifier([tuple(b) for b in config["mi_bands"]], int(config.get("csp_components", 2)), float(config.get("csp_regularization", .05)))
    model.fit(bands, y, rate, train_idx)
    score = model.evaluate({band: values[test_idx] for band, values in bands.items()}, y[test_idx])
    metadata = {"sample_rate": rate, "channel_count": X.shape[1], "channel_order": list(config["channel_order"]), "labels": {"0": "rest", "1": "left_hand_grasp"}, "bands": [list(b) for b in config["mi_bands"]], "validation_balanced_accuracy": score}
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path, metadata)
    print("[MODEL] saved=", model_path, "validation_balanced_accuracy=%.3f" % score)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="mi_config.json")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--data", type=Path, default=Path("data/left_hand.npz"))
    parser.add_argument("--model", type=Path, default=Path("artifacts/mi_model.joblib"))
    parser.add_argument("--trials-per-class", type=int, default=40)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.collect:
        collect(config, args.data, args.trials_per_class)
    else:
        train(config, args.data, args.model)

if __name__ == "__main__":
    main()
