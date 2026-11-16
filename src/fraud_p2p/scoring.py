"""Puntuación en línea: atributos, puntaje, nivel de acción, explicación y modelos en sombra.

El campeón decide. El retador, el retador entrenado con ataques y el centinela puntúan en sombra:
no cambian la decisión, pero sus alertas sobre operaciones que el campeón aprobó son la señal de que
el atacante pudo cambiar de táctica.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .constants import FEATURE_LABELS, FEATURES, RISK_TYPES, SENTINEL_FEATURES
from .features import Transaction, features_for_transaction
from .models import score, sigmoid

TIER_RED, TIER_AMBER, TIER_GREEN = "rojo", "ambar", "verde"
ACTIONS = {
    TIER_RED: "Retener los fondos y derivar a un analista",
    TIER_AMBER: "Pedir una verificación automática (código o huella)",
    TIER_GREEN: "Aprobar sin fricción",
}


@dataclass
class Decision:
    in_scope: bool
    tier: str
    action: str
    score: float | None = None
    probability: float | None = None
    contributions: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    shadow: dict[str, dict] = field(default_factory=dict)
    features: dict[str, float] = field(default_factory=dict)
    dest_ops_prev: int = 0
    dest_amount_prev: float = 0.0

    @property
    def tactic_change_signal(self) -> bool:
        """El campeón no alertó pero algún modelo de control sí."""
        return self.in_scope and self.tier != TIER_RED and any(v["alert"] for v in self.shadow.values())

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["tactic_change_signal"] = self.tactic_change_signal
        return d


class Scorer:
    """Carga los artefactos de `artifacts/` y puntúa operaciones individuales o lotes."""

    def __init__(self, artifacts_dir: str | Path) -> None:
        self.dir = Path(artifacts_dir)
        self.metadata = json.loads((self.dir / "metadata.json").read_text())
        self.models = {k: joblib.load(self.dir / "models" / v["file"]) for k, v in self.metadata["artifacts"].items()}
        t = self.metadata["thresholds"]
        self.red, self.amber = float(t["red"]), float(t["amber"])
        self.shadow_thresholds = {
            "challenger": t["challenger"],
            "challenger_adv": t["challenger_adv"],
            "sentinel": t["sentinel"],
        }
        champion = self.models["champion"]
        scaler, lr = champion.steps[0][1], champion.steps[-1][1]
        self._mean, self._scale = scaler.mean_, scaler.scale_
        self._coef, self._intercept = lr.coef_.ravel(), float(lr.intercept_[0])

    @property
    def model_version(self) -> str:
        return self.metadata["model_version"]

    def tier_for(self, s: float) -> str:
        return TIER_RED if s >= self.red else TIER_AMBER if s >= self.amber else TIER_GREEN

    def contributions(self, X: pd.DataFrame) -> np.ndarray:
        """Aporte de cada atributo al log-odds del campeón: coef * valor estandarizado."""
        return self._coef * (X[FEATURES].to_numpy() - self._mean) / self._scale

    def score_batch(self, X: pd.DataFrame) -> dict[str, np.ndarray]:
        cols = {"champion": FEATURES, "challenger": FEATURES, "challenger_adv": FEATURES, "sentinel": SENTINEL_FEATURES}
        return {k: score(m, X[cols[k]]) for k, m in self.models.items()}

    def score_transaction(self, tx: Transaction, dest_ops_prev: int, dest_amount_prev: float) -> Decision:
        if tx.type not in RISK_TYPES:
            return Decision(
                in_scope=False,
                tier=TIER_GREEN,
                action=ACTIONS[TIER_GREEN],
                reasons=[
                    f"{tx.type}: tipo de operación sin fraude observado en los datos; "
                    "se registra para el historial de la cuenta de destino."
                ],
                dest_ops_prev=dest_ops_prev,
                dest_amount_prev=dest_amount_prev,
            )
        X = features_for_transaction(tx, dest_ops_prev, dest_amount_prev)
        scores = self.score_batch(X)
        s = float(scores["champion"][0])
        contrib = self.contributions(X)[0]
        tier = self.tier_for(s)
        order = np.argsort(-contrib)
        reasons = [f"{FEATURE_LABELS[FEATURES[i]]} (+{contrib[i]:.1f})" for i in order[:3] if contrib[i] > 0.5]
        if not reasons:
            reasons = ["Ningún atributo empuja el puntaje hacia el fraude."]
        shadow = {
            k: {"score": float(scores[k][0]), "alert": bool(scores[k][0] >= u)}
            for k, u in self.shadow_thresholds.items()
        }
        return Decision(
            in_scope=True,
            tier=tier,
            action=ACTIONS[tier],
            score=s,
            probability=float(sigmoid(s)),
            contributions={FEATURES[i]: float(contrib[i]) for i in range(len(FEATURES))},
            reasons=reasons,
            shadow=shadow,
            features={k: float(v) for k, v in X.iloc[0].items()},
            dest_ops_prev=dest_ops_prev,
            dest_amount_prev=dest_amount_prev,
        )
