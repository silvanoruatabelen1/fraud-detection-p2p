"""KPI operativos, de negocio y de monitoreo sobre el tráfico reproducido.

Las legítimas del conjunto de demostración están submuestreadas: cada fila lleva su peso de muestreo
y los conteos se reponderan para estimar volúmenes reales. A escala de producción estas consultas
pasarían a vistas materializadas o a una capa analítica separada.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import sqlalchemy as sa

from fraud_p2p.constants import FEATURES
from fraud_p2p.economics import CostConfig, evaluate_alerts, optimal_threshold, serve_daily_queue
from fraud_p2p.monitoring import psi_report

from .db import decisions, reviews, transactions


def load_traffic(engine: sa.Engine, source: str = "replay") -> pd.DataFrame:
    q = (
        sa.select(
            transactions.c.id,
            transactions.c.step,
            transactions.c.day,
            transactions.c.hour,
            transactions.c.type,
            transactions.c.amount,
            transactions.c.label,
            transactions.c.sample_weight,
            decisions.c.in_scope,
            decisions.c.tier,
            decisions.c.score,
            decisions.c.dest_ops_prev,
            decisions.c.challenger_alert,
            decisions.c.challenger_adv_alert,
            decisions.c.sentinel_alert,
            decisions.c.tactic_signal,
            reviews.c.status,
        )
        .join(decisions, decisions.c.tx_id == transactions.c.id)
        .outerjoin(reviews, reviews.c.tx_id == transactions.c.id)
        .where(transactions.c.source == source)
    )
    with engine.connect() as conn:
        df = pd.read_sql(q, conn)
    df["w"] = df["sample_weight"].astype(float)
    df["is_red"] = df["tier"] == "rojo"
    df["is_amber"] = df["tier"] == "ambar"
    df["fraud"] = df["label"].fillna(0).astype(int) == 1
    return df


def _summary(g: pd.DataFrame, costs: CostConfig) -> dict:
    w = g["w"]
    red_w = float(w[g["is_red"]].sum())
    tp = float(w[g["is_red"] & g["fraud"]].sum())
    fp = float(w[g["is_red"] & ~g["fraud"]].sum())
    fn = float(w[~g["is_red"] & g["fraud"]].sum())
    protected = float(g.loc[g["is_red"] & g["fraud"], "amount"].sum())
    fraud_amount = float(g.loc[g["fraud"], "amount"].sum())
    savings = protected - costs.review_cost * red_w - costs.friction_cost * fp
    return {
        "operations": float(w.sum()),
        "in_scope": float(w[g["in_scope"]].sum()),
        "red": red_w,
        "amber": float(w[g["is_amber"]].sum()),
        "green": float(w[g["tier"] == "verde"].sum()),
        "frauds": float(w[g["fraud"]].sum()),
        "detected": tp,
        "missed": fn,
        "false_positives": fp,
        "recall": tp / (tp + fn) if tp + fn else None,
        "precision": tp / red_w if red_w else None,
        "fraud_amount": fraud_amount,
        "protected_amount": protected,
        "review_cost": costs.review_cost * red_w,
        "friction_cost": costs.friction_cost * fp,
        "net_savings": savings,
        "savings_pct": 100 * savings / fraud_amount if fraud_amount else None,
        "green_pct": 100 * float(w[g["tier"] == "verde"].sum()) / float(w.sum()) if len(g) else None,
        "tactic_signals": float(w[g["tactic_signal"]].sum()),
    }


def summary(df: pd.DataFrame, costs: CostConfig) -> dict:
    out = _summary(df, costs) if len(df) else {}
    out["last_step"] = int(df["step"].max()) if len(df) else None
    out["pending_reviews"] = int((df["is_red"] | df["is_amber"]).sum() - df["status"].notna().sum()) if len(df) else 0
    return out


def daily(df: pd.DataFrame, costs: CostConfig) -> list[dict]:
    return [{"day": int(d), **_summary(g, costs)} for d, g in df.groupby("day")]


def hourly(df: pd.DataFrame) -> list[dict]:
    g = (
        df.groupby(["day", "hour"])
        .apply(
            lambda x: pd.Series(
                {
                    "operations": x["w"].sum(),
                    "red": x.loc[x["is_red"], "w"].sum(),
                    "amber": x.loc[x["is_amber"], "w"].sum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    return g.to_dict("records")


def segments(df: pd.DataFrame) -> list[dict]:
    """Experiencia del cliente: fricción por segmento (franja horaria, historial del destino y tipo)."""
    d = df[df["in_scope"]].copy()
    d["franja"] = pd.cut(
        d["hour"],
        [-1, 5, 11, 17, 23],
        labels=["Madrugada<br>0-5 h", "Mañana<br>6-11 h", "Tarde<br>12-17 h", "Noche<br>18-23 h"],
    )
    d["historial"] = np.where(d["dest_ops_prev"] > 0, "Destino con historial", "Destino nuevo")
    rows = []
    for dim in ("franja", "historial", "type"):
        for val, g in d.groupby(dim, observed=True):
            legit = g[~g["fraud"]]
            lw = legit["w"].sum()
            rows.append(
                {
                    "dimension": dim,
                    "segment": str(val),
                    "legit_operations": float(lw),
                    "amber_legit": float(legit.loc[legit["is_amber"], "w"].sum()),
                    "red_legit": float(legit.loc[legit["is_red"], "w"].sum()),
                    "friction_rate_pct": 100 * float(legit.loc[legit["is_amber"] | legit["is_red"], "w"].sum()) / lw
                    if lw
                    else 0.0,
                    # Fricción que generarían los modelos de control si decidieran (hoy corren en sombra)
                    "control_rate_pct": 100
                    * float(legit.loc[legit["challenger_adv_alert"] | legit["sentinel_alert"], "w"].sum())
                    / lw
                    if lw
                    else 0.0,
                }
            )
    return rows


def drift(engine: sa.Engine, reference: dict, window_hours: int = 72) -> list[dict]:
    """PSI de las últimas `window_hours` horas de tráfico frente a entrenamiento.

    La ventana debe cubrir días completos: con menos de 24 h, los atributos horarios muestran una
    deriva artificial. Las filas se ponderan por su peso de muestreo.
    """
    t = transactions
    with engine.connect() as conn:
        last = conn.execute(sa.select(sa.func.max(t.c.step)).where(t.c.source == "replay")).scalar()
        if last is None:
            return []
        q = (
            sa.select(decisions.c.features, decisions.c.score, t.c.sample_weight)
            .join(t, t.c.id == decisions.c.tx_id)
            .where(decisions.c.in_scope.is_(True), t.c.source == "replay", t.c.step > last - window_hours)
        )
        rows = conn.execute(q).all()
    if not rows:
        return []
    X = pd.DataFrame([r[0] for r in rows])[FEATURES]
    rep = psi_report(reference, X, np.array([r[1] for r in rows]), np.array([r[2] for r in rows], dtype=float))
    rep["estado"] = rep["estado"].astype(str)
    return rep.to_dict("records")


class WhatIf:
    """Recalcula el umbral en validación con otros costos o cupo y lo aplica a la prueba con cola diaria."""

    def __init__(self, validation: pd.DataFrame, test: pd.DataFrame) -> None:
        self.va, self.te = validation, test
        self.va_days = (self.va["step"].to_numpy() - 1) // 24 + 1
        self.te_days = (self.te["step"].to_numpy() - 1) // 24 + 1

    def run(self, costs: CostConfig) -> dict:
        o = optimal_threshold(
            self.va["y"].to_numpy(),
            self.va["score"].to_numpy().astype(np.float64),
            self.va["amount"].to_numpy(),
            self.va_days,
            costs,
        )
        cand = self.te["score"].to_numpy() >= o["threshold"]
        served = serve_daily_queue(cand, self.te_days, costs.daily_capacity)
        e = evaluate_alerts(self.te["y"].to_numpy(), served, self.te["amount"].to_numpy(), 16, costs)
        curve = o["curve"]
        sample = curve.iloc[np.linspace(0, len(curve) - 1, min(400, len(curve))).astype(int)]
        return {
            "threshold": o["threshold"],
            "band": [o["band_min"], o["band_max"]],
            "test": {**e, "savings_pct": 100 * e["savings"] / e["fraud_amount"], "candidates": int(cand.sum())},
            "curve": sample[["threshold", "savings", "max_daily", "feasible"]].to_dict("records"),
        }
