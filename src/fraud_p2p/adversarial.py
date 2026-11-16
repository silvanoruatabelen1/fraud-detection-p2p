"""Simulación del atacante que cambia de táctica, y aumentación de datos con retiros parciales."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import build_features


def features_with(gold: pd.DataFrame, idx: np.ndarray, *, amount=None, balance=None, is_transfer=None,
                  hour=None, ops_prev=None, amount_prev=None) -> pd.DataFrame:
    """Recalcula los atributos de las filas `idx` reemplazando las variables que controla el atacante."""
    g = gold.iloc[idx]
    return build_features(
        g["amount"].to_numpy() if amount is None else amount,
        g["oldbalanceOrg"].to_numpy() if balance is None else balance,
        (g["type"] == "TRANSFER").to_numpy() if is_transfer is None else is_transfer,
        (g["step"] % 24).to_numpy() if hour is None else hour,
        g["dest_ops_prev"].to_numpy() if ops_prev is None else ops_prev,
        g["dest_amount_prev"].to_numpy() if amount_prev is None else amount_prev,
    )


def partial_withdrawal(gold: pd.DataFrame, idx: np.ndarray, fraction: float) -> np.ndarray:
    """Monto de un fraude que retira solo una fracción del saldo (si la cuenta tiene saldo)."""
    balance = gold["oldbalanceOrg"].to_numpy()[idx]
    amount = gold["amount"].to_numpy()[idx]
    return np.where(balance > 0, np.round(fraction * balance, 2), amount)


def augment_partial_withdrawals(gold: pd.DataFrame, mask: np.ndarray, copies: int,
                                rng: np.random.Generator) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Copias sintéticas de los fraudes con saldo que retiran entre el 50% y el 99% del saldo.

    Devuelve atributos, montos y steps de las copias. Las copias son versiones alternativas de los
    mismos fraudes, no tráfico adicional: no deben ocupar cupo de revisión al fijar el umbral.
    """
    y = gold["isFraud"].to_numpy()
    balance = gold["oldbalanceOrg"].to_numpy()
    idx = np.where(mask & (y == 1) & (balance > 0))[0]
    frames, amounts = [], []
    for _ in range(copies):
        m = np.round(rng.uniform(0.5, 0.99, len(idx)) * balance[idx], 2)
        frames.append(features_with(gold, idx, amount=m))
        amounts.append(m)
    steps = np.tile(gold["step"].to_numpy()[idx], copies)
    return pd.concat(frames, ignore_index=True), np.concatenate(amounts), steps
