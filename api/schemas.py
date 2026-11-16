from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TxType = Literal["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]


class TransactionIn(BaseModel):
    step: int = Field(..., ge=1, le=10_000, description="Hora de la simulación (1 = primera hora del día 1)")
    type: TxType
    amount: float = Field(..., ge=0)
    old_balance_orig: float = Field(..., ge=0, description="Saldo de la cuenta de origen antes de operar")
    name_dest: str = Field(..., min_length=1, max_length=20)
    name_orig: str = Field("", max_length=20)
    label: int | None = Field(
        None, ge=0, le=1, description="Solo para reproducir datos etiquetados; el modelo no la usa"
    )
    sample_weight: float = Field(1.0, gt=0)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "step": 400,
                    "type": "TRANSFER",
                    "amount": 181000.0,
                    "old_balance_orig": 181000.0,
                    "name_dest": "C553264065",
                    "name_orig": "C1305486145",
                }
            ]
        }
    }


class ShadowOut(BaseModel):
    score: float
    alert: bool


class DecisionOut(BaseModel):
    tx_id: int | None
    model_version: str
    in_scope: bool
    tier: Literal["rojo", "ambar", "verde"]
    action: str
    score: float | None
    probability: float | None
    reasons: list[str]
    contributions: dict[str, float]
    shadow: dict[str, ShadowOut]
    tactic_change_signal: bool
    dest_ops_prev: int
    dest_amount_prev: float
    latency_ms: float


class BatchIn(BaseModel):
    transactions: list[TransactionIn] = Field(..., max_length=5_000)
    source: Literal["replay", "simulator"] = "replay"


class BatchOut(BaseModel):
    processed: int
    red: int
    amber: int
    last_step: int


class ReviewIn(BaseModel):
    status: Literal["fraude_confirmado", "liberado"]
    analyst: str = "analista"
