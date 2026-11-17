from __future__ import annotations
import random

def trial_order(trials_per_class: int, seed: int = 7) -> list[int]:
    labels = [0] * trials_per_class + [1] * trials_per_class
    random.Random(seed).shuffle(labels)
    return labels

def announce(label: int, seconds: float) -> None:
    text = "REST" if label == 0 else "LEFT HAND: imagine grasping"
    print("\n>>> %s for %.1f seconds <<<" % (text, seconds), flush=True)
