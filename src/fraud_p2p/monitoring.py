"""Monitoreo de deriva: índice de estabilidad poblacional (PSI) por atributo y del puntaje.

Convención usual: PSI < 0,10 estable; 0,10 a 0,25 cambio moderado; > 0,25 cambio relevante.
La referencia se calcula con los datos de entrenamiento y viaja en metadata.json.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-6


def _edges(x: np.ndarray, bins: int = 10) -> list[float]:
    qs = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)))
    if len(qs) <= 2:  # atributo binario o casi constante: un corte entre los dos valores
        vals = np.unique(x)
        return [float(-np.inf), *((vals[:-1] + vals[1:]) / 2).tolist(), float(np.inf)]
    return [float(-np.inf), *qs[1:-1].tolist(), float(np.inf)]


def _proportions(x: np.ndarray, edges: list[float]) -> list[float]:
    counts, _ = np.histogram(x, bins=np.asarray(edges))
    return (counts / max(counts.sum(), 1)).tolist()


def build_reference(X: pd.DataFrame, scores: np.ndarray) -> dict:
    ref = {}
    for col in X.columns:
        e = _edges(X[col].to_numpy())
        ref[col] = {"edges": e, "proportions": _proportions(X[col].to_numpy(), e)}
    e = _edges(np.asarray(scores))
    ref["__score__"] = {"edges": e, "proportions": _proportions(np.asarray(scores), e)}
    return ref


def psi(expected: list[float], actual: list[float]) -> float:
    e = np.clip(np.asarray(expected, dtype=float), EPS, None)
    a = np.clip(np.asarray(actual, dtype=float), EPS, None)
    return float(np.sum((a - e) * np.log(a / e)))


def psi_report(reference: dict, X: pd.DataFrame, scores: np.ndarray | None = None) -> pd.DataFrame:
    rows = []
    for col in X.columns:
        if col not in reference:
            continue
        r = reference[col]
        rows.append({"variable": col, "psi": psi(r["proportions"], _proportions(X[col].to_numpy(), r["edges"]))})
    if scores is not None and "__score__" in reference:
        r = reference["__score__"]
        rows.append({"variable": "__score__", "psi": psi(r["proportions"], _proportions(np.asarray(scores), r["edges"]))})
    out = pd.DataFrame(rows)
    out["estado"] = pd.cut(out["psi"], [-np.inf, 0.10, 0.25, np.inf], labels=["estable", "moderado", "relevante"])
    return out
