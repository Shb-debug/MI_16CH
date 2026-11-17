from __future__ import annotations
import numpy as np

def normalized_covariance(epoch: np.ndarray) -> np.ndarray:
    values = epoch - np.mean(epoch, axis=1, keepdims=True)
    covariance = values @ values.T / max(values.shape[1] - 1, 1)
    return covariance / max(float(np.trace(covariance)), 1e-12)

class RegularizedCSP:
    def __init__(self, components: int = 2, regularization: float = 0.05) -> None:
        self.components = int(components)
        self.regularization = float(regularization)
        self.filters: np.ndarray | None = None

    def fit(self, class_zero: np.ndarray, class_one: np.ndarray) -> "RegularizedCSP":
        c0 = np.mean([normalized_covariance(x) for x in class_zero], axis=0)
        c1 = np.mean([normalized_covariance(x) for x in class_one], axis=0)
        n = c0.shape[0]
        composite = c0 + c1 + self.regularization * np.trace(c0 + c1) / n * np.eye(n)
        values, vectors = np.linalg.eigh(composite)
        whitening = vectors @ np.diag(1.0 / np.sqrt(np.maximum(values, 1e-12))) @ vectors.T
        eig_values, eig_vectors = np.linalg.eigh(whitening @ c1 @ whitening.T)
        eig_vectors = eig_vectors[:, np.argsort(eig_values)[::-1]]
        m = min(self.components, n // 2)
        selected = np.column_stack((eig_vectors[:, :m], eig_vectors[:, -m:]))
        self.filters = selected.T @ whitening
        return self

    def transform(self, epochs: np.ndarray) -> np.ndarray:
        if self.filters is None:
            raise RuntimeError("CSP is not fitted")
        values = np.asarray(epochs, dtype=np.float64)
        if values.ndim == 2:
            values = values[None, :, :]
        projected = np.einsum("kc,nct->nkt", self.filters, values)
        power = np.var(projected, axis=2)
        return np.log(power / np.maximum(np.sum(power, axis=1, keepdims=True), 1e-12) + 1e-12)
