from __future__ import annotations
from pathlib import Path
from typing import Any
import joblib
import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import balanced_accuracy_score
from sklearn.preprocessing import StandardScaler
from features_fbcsp import RegularizedCSP

class FBCSPClassifier:
    def __init__(self, bands: list[tuple[float, float]], components: int = 2, regularization: float = .05) -> None:
        self.bands = [tuple(b) for b in bands]
        self.components, self.regularization = components, regularization
        self.csp: list[RegularizedCSP] = []
        self.scaler = StandardScaler()
        self.classifier = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
        self.sample_rate = 0.0
        self.channel_count = 0
        self.model_version = "fbcsp-left-hand-v1"

    def fit(self, band_epochs: dict[tuple[float, float], np.ndarray], labels: np.ndarray, sample_rate: float, train_idx: np.ndarray | None = None) -> None:
        labels = np.asarray(labels, dtype=np.int64).ravel()
        if set(np.unique(labels)) != {0, 1}:
            raise ValueError("labels must contain 0=rest and 1=left_hand_grasp")
        first = band_epochs[self.bands[0]]
        self.sample_rate, self.channel_count = float(sample_rate), int(first.shape[1])
        self.csp, blocks = [], []
        fit_idx = np.arange(len(labels)) if train_idx is None else np.asarray(train_idx, dtype=int)
        for band in self.bands:
            fit_labels = labels[fit_idx]
            csp = RegularizedCSP(self.components, self.regularization).fit(
                band_epochs[band][fit_idx][fit_labels == 0],
                band_epochs[band][fit_idx][fit_labels == 1],
            )
            self.csp.append(csp)
            blocks.append(csp.transform(band_epochs[band]))
        matrix = np.concatenate(blocks, axis=1)
        self.scaler.fit(matrix[fit_idx])
        self.classifier.fit(self.scaler.transform(matrix[fit_idx]), labels[fit_idx])

    def transform(self, band_epochs: dict[tuple[float, float], np.ndarray]) -> np.ndarray:
        return np.concatenate([csp.transform(band_epochs[band]) for csp, band in zip(self.csp, self.bands)], axis=1)

    def predict_proba(self, band_epochs: dict[tuple[float, float], np.ndarray]) -> float:
        return float(self.classifier.predict_proba(self.scaler.transform(self.transform(band_epochs)))[0, 1])

    def evaluate(self, band_epochs: dict[tuple[float, float], np.ndarray], labels: np.ndarray) -> float:
        predicted = self.classifier.predict(self.scaler.transform(self.transform(band_epochs)))
        return float(balanced_accuracy_score(labels, predicted))

    def save(self, path: str | Path, metadata: dict[str, Any]) -> None:
        joblib.dump({"model": self, "metadata": metadata, "model_version": self.model_version}, path)

    @staticmethod
    def load(path: str | Path) -> tuple["FBCSPClassifier", dict[str, Any]]:
        payload = joblib.load(path)
        return payload["model"], payload.get("metadata", {})
