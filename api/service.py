"""Lógica de puntuación con persistencia. El historial del destino se calcula desde la base de datos,
que es la fuente de verdad: la API no guarda estado en memoria y puede escalar horizontalmente."""

from __future__ import annotations

import time
from collections.abc import Sequence

import numpy as np
import pandas as pd
import sqlalchemy as sa

from fraud_p2p.constants import FEATURE_LABELS, FEATURES, HISTORY_WINDOW_H, RISK_TYPES, day_of_step
from fraud_p2p.features import Transaction, build_features
from fraud_p2p.scoring import ACTIONS, TIER_AMBER, TIER_GREEN, TIER_RED, Scorer

from .db import decisions, transactions
from .schemas import TransactionIn


def history_for(conn: sa.Connection, dests: Sequence[str], step: int) -> dict[str, tuple[int, float]]:
    """Operaciones y monto recibidos por cada destino en [step - 168, step). Excluye la hora en curso."""
    if not dests:
        return {}
    q = (sa.select(transactions.c.name_dest, sa.func.count(), sa.func.coalesce(sa.func.sum(transactions.c.amount), 0.0))
         .where(transactions.c.name_dest.in_(list(set(dests))),
                transactions.c.step >= step - HISTORY_WINDOW_H, transactions.c.step < step)
         .group_by(transactions.c.name_dest))
    return {d: (int(n), float(s)) for d, n, s in conn.execute(q)}


def _reasons(contrib_row: np.ndarray) -> str:
    order = np.argsort(-contrib_row)
    parts = [f"{FEATURE_LABELS[FEATURES[i]]} (+{contrib_row[i]:.1f})" for i in order[:3] if contrib_row[i] > 0.5]
    return " · ".join(parts) if parts else "Ningún atributo empuja el puntaje hacia el fraude."


class ScoringService:
    def __init__(self, engine: sa.Engine, scorer: Scorer) -> None:
        self.engine = engine
        self.scorer = scorer

    def score_one(self, tx: TransactionIn, persist: bool, source: str) -> dict:
        t0 = time.perf_counter()
        with self.engine.begin() as conn:
            ops, amt = history_for(conn, [tx.name_dest], tx.step).get(tx.name_dest, (0, 0.0))
            d = self.scorer.score_transaction(
                Transaction(step=tx.step, type=tx.type, amount=tx.amount, old_balance_orig=tx.old_balance_orig,
                            name_dest=tx.name_dest, name_orig=tx.name_orig), ops, amt)
            latency = (time.perf_counter() - t0) * 1000
            tx_id = None
            if persist:
                tx_id = conn.execute(transactions.insert().returning(transactions.c.id), [self._tx_row(tx, source)]).scalar_one()
                conn.execute(decisions.insert(), [{
                    "tx_id": tx_id, "model_version": self.scorer.model_version, "in_scope": d.in_scope, "tier": d.tier,
                    "score": d.score, "probability": d.probability, "dest_ops_prev": ops,
                    "challenger_alert": d.shadow.get("challenger", {}).get("alert", False),
                    "challenger_adv_alert": d.shadow.get("challenger_adv", {}).get("alert", False),
                    "sentinel_alert": d.shadow.get("sentinel", {}).get("alert", False),
                    "tactic_signal": d.tactic_change_signal, "reasons": " · ".join(d.reasons),
                    "features": d.features or None, "contributions": d.contributions or None, "latency_ms": latency}])
        return {"tx_id": tx_id, "model_version": self.scorer.model_version, **d.to_dict(), "latency_ms": latency}

    def score_batch(self, txs: list[TransactionIn], source: str) -> dict:
        """Procesa por hora: todas las operaciones de un step ven el mismo historial (steps anteriores)."""
        df = pd.DataFrame([t.model_dump() for t in txs]).sort_values("step", kind="mergesort")
        red = amber = 0
        with self.engine.begin() as conn:
            for step, g in df.groupby("step", sort=True):
                t0 = time.perf_counter()
                hist = history_for(conn, g["name_dest"].tolist(), int(step))
                ops = np.array([hist.get(d, (0, 0.0))[0] for d in g["name_dest"]])
                amt = np.array([hist.get(d, (0, 0.0))[1] for d in g["name_dest"]])
                ids = conn.execute(transactions.insert().returning(transactions.c.id, sort_by_parameter_order=True),
                                   [self._tx_row(TransactionIn(**r), source) for r in g.to_dict("records")]).scalars().all()
                in_scope = g["type"].isin(RISK_TYPES).to_numpy()
                rows = [{"tx_id": i, "model_version": self.scorer.model_version, "in_scope": False, "tier": TIER_GREEN,
                         "dest_ops_prev": int(o), "reasons": "Tipo de operación sin fraude observado"} for i, o in zip(ids, ops, strict=True)]
                if in_scope.any():
                    gi = g[in_scope]
                    X = build_features(gi["amount"].to_numpy(), gi["old_balance_orig"].to_numpy(),
                                       (gi["type"] == "TRANSFER").to_numpy(), (gi["step"] % 24).to_numpy(),
                                       ops[in_scope], amt[in_scope])
                    s = self.scorer.score_batch(X)
                    contrib = self.scorer.contributions(X)
                    lat = (time.perf_counter() - t0) * 1000 / len(g)
                    for j, k in enumerate(np.where(in_scope)[0]):
                        sc = float(s["champion"][j])
                        tier = self.scorer.tier_for(sc)
                        sh = {n: bool(s[n][j] >= u) for n, u in self.scorer.shadow_thresholds.items()}
                        red += tier == TIER_RED
                        amber += tier == TIER_AMBER
                        rows[k].update({
                            "in_scope": True, "tier": tier, "score": sc, "probability": float(1 / (1 + np.exp(-sc))),
                            "challenger_alert": sh["challenger"], "challenger_adv_alert": sh["challenger_adv"],
                            "sentinel_alert": sh["sentinel"], "tactic_signal": tier != TIER_RED and any(sh.values()),
                            "reasons": _reasons(contrib[j]), "latency_ms": lat,
                            "features": {f: float(X.iloc[j][f]) for f in FEATURES},
                            "contributions": {f: float(contrib[j][i]) for i, f in enumerate(FEATURES)}})
                conn.execute(decisions.insert(), rows)
        return {"processed": len(df), "red": int(red), "amber": int(amber), "last_step": int(df["step"].max())}

    @staticmethod
    def _tx_row(tx: TransactionIn, source: str) -> dict:
        return {"step": tx.step, "day": int(day_of_step(tx.step)), "hour": tx.step % 24, "type": tx.type,
                "amount": tx.amount, "name_orig": tx.name_orig, "old_balance_orig": tx.old_balance_orig,
                "name_dest": tx.name_dest, "source": source, "label": tx.label, "sample_weight": tx.sample_weight}


ACTIONS_BY_TIER = ACTIONS
