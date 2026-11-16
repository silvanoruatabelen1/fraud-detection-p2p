"""Atributos ex ante. Una sola definición para entrenar, evaluar, simular ataques y servir.

Toda la información usada existe en el instante de autorizar la operación: el monto, el saldo previo
de la cuenta de origen, el tipo, la hora y el historial del destino en las 168 h anteriores, sin
incluir la hora en curso. Se excluyen los saldos posteriores (fuga de información) y los identificadores.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .constants import FEATURES, HISTORY_WINDOW_H, TRANCHE_10M
from .data import risk_mask


def build_features(
    amount: np.ndarray,
    balance: np.ndarray,
    is_transfer: np.ndarray,
    hour: np.ndarray,
    dest_ops_prev: np.ndarray,
    dest_amount_prev: np.ndarray,
) -> pd.DataFrame:
    """Los 12 atributos del modelo. Las comparaciones monto-saldo se hacen al centavo, en enteros."""
    amount = np.asarray(amount, dtype=np.float64)
    balance = np.asarray(balance, dtype=np.float64)
    hour = np.asarray(hour, dtype=np.float64)
    cents_amount = np.round(amount * 100).astype(np.int64)
    cents_balance = np.round(balance * 100).astype(np.int64)
    return pd.DataFrame(
        {
            "es_transfer": np.asarray(is_transfer).astype(np.int8),
            "log_monto": np.log10(1 + amount),
            "log_saldo_orig": np.log10(1 + balance),
            "emisor_sin_saldo": (cents_balance == 0).astype(np.int8),
            "monto_excede_saldo": (cents_amount > cents_balance).astype(np.int8),
            "log_ratio_monto_saldo": np.log10((1 + amount) / (1 + balance)),
            "marca_vaciamiento": (cents_amount == cents_balance).astype(np.int8),
            "tramo_10m_con_saldo": ((amount == TRANCHE_10M) & (balance >= TRANCHE_10M)).astype(np.int8),
            "hora_sen": np.sin(2 * np.pi * hour / 24),
            "hora_cos": np.cos(2 * np.pi * hour / 24),
            "dest_ops_previas_log": np.log10(1 + np.asarray(dest_ops_prev, dtype=np.float64)),
            "dest_monto_previo_log": np.log10(1 + np.asarray(dest_amount_prev, dtype=np.float64)),
        },
        columns=FEATURES,
    )


def destination_history(df: pd.DataFrame, window_h: int = HISTORY_WINDOW_H) -> pd.DataFrame:
    """Historial vectorizado por (destino, step): operaciones y monto recibidos en [t - window_h, t).

    Se cuentan las operaciones de cualquier tipo hacia los destinos que aparecen en el subespacio
    de riesgo. `closed="left"` excluye la hora en curso, que es lo que hace causal a la ventana.
    """
    dests = pd.Index(df.loc[risk_mask(df), "nameDest"].unique())
    hist = (
        df.loc[df["nameDest"].isin(dests), ["nameDest", "step", "amount"]]
        .groupby(["nameDest", "step"], observed=True)
        .agg(ops=("amount", "size"), monto=("amount", "sum"))
        .reset_index()
        .sort_values(["nameDest", "step"], kind="mergesort")
    )
    hist["t"] = pd.to_timedelta(hist["step"].astype("int64"), unit="h")
    roll = (
        hist.set_index("t")
        .groupby("nameDest", sort=False)[["ops", "monto"]]
        .rolling(f"{window_h}h", closed="left")
        .sum()
    )
    hist["dest_ops_prev"] = roll["ops"].fillna(0).to_numpy()
    hist["dest_amount_prev"] = roll["monto"].fillna(0).to_numpy()
    return hist[["nameDest", "step", "dest_ops_prev", "dest_amount_prev"]]


def build_gold(curated: pd.DataFrame) -> pd.DataFrame:
    """Capa oro: atributos, etiqueta y metadatos del subespacio de riesgo, en orden cronológico."""
    hist = destination_history(curated)
    cols = ["step", "type", "amount", "oldbalanceOrg", "nameOrig", "nameDest", "isFraud", "isFlaggedFraud"]
    risk = (
        curated.loc[risk_mask(curated), cols]
        .merge(hist, on=["nameDest", "step"], how="left")
        .reset_index(drop=True)
    )
    risk[["dest_ops_prev", "dest_amount_prev"]] = risk[["dest_ops_prev", "dest_amount_prev"]].fillna(0)
    X = build_features(
        risk["amount"].to_numpy(),
        risk["oldbalanceOrg"].to_numpy(),
        (risk["type"].astype(str) == "TRANSFER").to_numpy(),
        (risk["step"] % 24).to_numpy(),
        risk["dest_ops_prev"].to_numpy(),
        risk["dest_amount_prev"].to_numpy(),
    )
    meta = risk[["step", "type", "amount", "oldbalanceOrg", "nameOrig", "nameDest", "isFraud", "isFlaggedFraud",
                 "dest_ops_prev", "dest_amount_prev"]].copy()
    meta["type"] = meta["type"].astype(str)
    return pd.concat([meta, X], axis=1)


@dataclass(frozen=True)
class Transaction:
    """Operación tal como llega al autorizador. Solo campos conocidos antes de ejecutarla."""

    step: int
    type: str
    amount: float
    old_balance_orig: float
    name_dest: str
    name_orig: str = ""

    @property
    def hour(self) -> int:
        return self.step % 24


def features_for_transaction(tx: Transaction, dest_ops_prev: float, dest_amount_prev: float) -> pd.DataFrame:
    """Atributos de una operación individual con la misma función que el entrenamiento."""
    return build_features(
        np.array([tx.amount]),
        np.array([tx.old_balance_orig]),
        np.array([tx.type == "TRANSFER"]),
        np.array([tx.hour]),
        np.array([dest_ops_prev]),
        np.array([dest_amount_prev]),
    )


class InMemoryHistory:
    """Historial en línea del destino para pruebas y ejecución sin base de datos.

    Mantiene, por destino, los eventos de las últimas `window_h` horas. La consulta en el step t
    suma solo los eventos con step en [t - window_h, t): una operación nunca se ve a sí misma.
    """

    def __init__(self, window_h: int = HISTORY_WINDOW_H) -> None:
        self.window_h = window_h
        self._events: dict[str, deque[tuple[int, float]]] = defaultdict(deque)

    def add(self, dest: str, step: int, amount: float) -> None:
        self._events[dest].append((step, amount))

    def query(self, dest: str, step: int) -> tuple[int, float]:
        events = self._events.get(dest)
        if not events:
            return 0, 0.0
        while events and events[0][0] < step - self.window_h:
            events.popleft()
        ops, total = 0, 0.0
        for s, a in events:
            if s >= step:
                break
            ops += 1
            total += a
        return ops, total
