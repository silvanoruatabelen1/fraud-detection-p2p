"""Umbral económico con cupo diario de revisión y cola de atención.

El ahorro de un umbral es el monto de los fraudes detenidos menos el costo de revisar cada alerta
y la fricción de retener a un cliente honesto. Un umbral es factible si ningún día supera el cupo de
revisiones. El umbral elegido es el punto medio de la franja factible con al menos el 99,9% del
ahorro máximo: los bordes quedan fijados por una sola operación de validación y el centro deja el
mayor margen frente a lo no observado.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostConfig:
    review_cost: float = 1_500.0  # u.m. por alerta revisada (supuesto)
    friction_cost: float = 8_500.0  # u.m. adicionales por cliente honesto retenido (supuesto)
    daily_capacity: int = 1_000  # alertas que el equipo puede revisar por día (supuesto)
    tolerance: float = 0.999  # franja: umbrales con al menos este porcentaje del ahorro máximo


def savings_curve(y, score, amount, days, costs: CostConfig = CostConfig(), counts=None) -> pd.DataFrame:
    """Ahorro y alertas para cada umbral posible (uno por puntaje distinto)."""
    y, score, amount, days = map(np.asarray, (y, score, amount, days))
    order = np.argsort(-score, kind="mergesort")
    ss, yy, mm, dd = score[order], y[order], amount[order], days[order]
    tp, fp, saved = np.cumsum(yy), np.cumsum(1 - yy), np.cumsum(mm * yy)
    last = np.r_[ss[1:] != ss[:-1], True]  # último elemento de cada grupo de puntajes empatados
    occupies = np.ones(len(dd), dtype=bool) if counts is None else np.asarray(counts)[order]
    max_daily = np.zeros(int(last.sum()), dtype=np.int64)
    for d in np.unique(dd):
        max_daily = np.maximum(max_daily, np.cumsum((dd == d) & occupies)[last])
    c = pd.DataFrame({"threshold": ss[last], "tp": tp[last], "fp": fp[last], "saved": saved[last]})
    c["alerts_per_day"] = (c["tp"] + c["fp"]) / len(np.unique(dd))
    c["max_daily"] = max_daily
    c["savings"] = c["saved"] - costs.review_cost * (c["tp"] + c["fp"]) - costs.friction_cost * c["fp"]
    c["feasible"] = c["max_daily"] <= costs.daily_capacity
    return c


def evaluate_alerts(y, alerts, amount, n_days: int, costs: CostConfig = CostConfig()) -> dict:
    """Resultado económico de un vector booleano de alertas atendidas."""
    y, a, amount = np.asarray(y), np.asarray(alerts, dtype=bool), np.asarray(amount)
    tp, fp = int((a & (y == 1)).sum()), int((a & (y == 0)).sum())
    saved = float(amount[a & (y == 1)].sum())
    n_alerts = int(a.sum())
    return {
        "alerts": n_alerts,
        "tp": tp,
        "fp": fp,
        "fn": int(y.sum()) - tp,
        "alerts_per_day": n_alerts / n_days,
        "recall": tp / y.sum() if y.sum() else float("nan"),
        "precision": tp / n_alerts if n_alerts else float("nan"),
        "saved": saved,
        "savings": saved - costs.review_cost * n_alerts - costs.friction_cost * fp,
        "fraud_amount": float(amount[y == 1].sum()),
    }


def optimal_threshold(y, score, amount, days, costs: CostConfig = CostConfig(), counts=None) -> dict:
    """Punto medio de la franja factible con al menos `tolerance` del ahorro máximo."""
    score = np.asarray(score)
    c = savings_curve(y, score, amount, days, costs, counts)
    n_days = len(np.unique(days))
    feasible = c[c["feasible"]]
    if feasible.empty or feasible["savings"].max() <= 0:  # ningún umbral factible ahorra: no se alerta
        u = float(np.nextafter(score.max(), np.inf))
        return {
            "threshold": u,
            "band_min": u,
            "band_max": u,
            **evaluate_alerts(y, score >= u, amount, n_days, costs),
            "curve": c,
        }
    best = feasible["savings"].max()
    band = feasible[feasible["savings"] >= costs.tolerance * best]
    lo, hi = float(band["threshold"].min()), float(band["threshold"].max())
    u = (lo + hi) / 2
    effective = c.loc[c["threshold"] >= u].iloc[-1]
    if not effective["feasible"] or effective["savings"] < costs.tolerance * best:
        u = float(band.loc[(band["threshold"] - u).abs().idxmin(), "threshold"])  # el punto medio cayó en un hueco
    return {
        "threshold": u,
        "band_min": lo,
        "band_max": hi,
        **evaluate_alerts(y, score >= u, amount, n_days, costs),
        "curve": c,
    }


def serve_daily_queue(candidates, days, capacity: int) -> np.ndarray:
    """Cola de atención: cada día se atienden las primeras `capacity` alertas en orden de llegada."""
    candidates = np.asarray(candidates, dtype=bool)
    turn = pd.Series(candidates).groupby(np.asarray(days), sort=False).cumsum().to_numpy()
    return candidates & (turn <= capacity)


def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Intervalo de Wilson al 95% para una proporción; apto para eventos raros."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return max(0.0, center - half), min(1.0, center + half)
