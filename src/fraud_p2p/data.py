"""Ingesta y curación de PaySim en capas (bronce, plata, oro) sobre Parquet.

- Bronce: el CSV original, tipado (montos en float64) y validado.
- Plata: la base curada, ordenada de forma estable por step y con el indicador de destino comerciante.
- Oro: la matriz de atributos del subespacio de riesgo, lista para entrenar.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import RAW_COLUMNS, RISK_TYPES, TRANSACTION_TYPES

log = logging.getLogger(__name__)


class SchemaError(ValueError):
    """Los datos no cumplen el contrato de entrada."""


def validate_raw(df: pd.DataFrame) -> None:
    """Contrato mínimo del CSV de PaySim. Falla rápido y con un mensaje accionable."""
    missing = set(RAW_COLUMNS) - set(df.columns)
    if missing:
        raise SchemaError(f"Faltan columnas: {sorted(missing)}")
    unknown = set(df["type"].astype(str).unique()) - set(TRANSACTION_TYPES)
    if unknown:
        raise SchemaError(f"Tipos de operación desconocidos: {sorted(unknown)}")
    money = ["amount", "oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]
    if (df[money] < 0).any().any():
        raise SchemaError("Hay montos o saldos negativos")
    if df[money].isna().any().any() or df[["nameOrig", "nameDest"]].isna().any().any():
        raise SchemaError("Hay valores nulos en montos, saldos o cuentas")
    if not df["isFraud"].isin([0, 1]).all():
        raise SchemaError("isFraud debe ser 0 o 1")
    if df["step"].min() < 1:
        raise SchemaError("step debe empezar en 1")


def read_raw_csv(path: str | Path) -> pd.DataFrame:
    """Lee el CSV original. Los montos se leen en float64: en float32 se pierde el centavo."""
    df = pd.read_csv(path, dtype=RAW_COLUMNS)
    validate_raw(df)
    log.info("CSV leído: %s filas", f"{len(df):,}")
    return df


def curate(df: pd.DataFrame) -> pd.DataFrame:
    """Base curada (plata): mismas columnas, orden cronológico estable y destino comerciante."""
    out = df[list(RAW_COLUMNS)].copy()
    out["type"] = pd.Categorical(out["type"].astype(str), categories=list(TRANSACTION_TYPES))
    out["dest_es_comerciante"] = out["nameDest"].str.startswith("M").astype("int8")
    return out.sort_values("step", kind="mergesort").reset_index(drop=True)


def risk_mask(df: pd.DataFrame) -> np.ndarray:
    return df["type"].astype(str).isin(RISK_TYPES).to_numpy()


def write_parquet(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    log.info("Escrito %s (%s filas)", path, f"{len(df):,}")
    return path
