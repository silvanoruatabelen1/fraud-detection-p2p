"""API de puntuación y operación del sistema antifraude.

uvicorn api.main:app --reload
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

import pandas as pd
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from fraud_p2p import __version__
from fraud_p2p.economics import CostConfig
from fraud_p2p.scoring import Scorer

from . import analytics
from .db import decisions, init_db, make_engine, reviews, seed_history, transactions
from .schemas import BatchIn, BatchOut, DecisionOut, ReviewIn, TransactionIn
from .service import ScoringService
from .settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")
state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine(settings.database_url)
    init_db(engine)
    if settings.seed_on_startup:
        seed_history(engine, settings.demo_data_dir)
    scorer = Scorer(settings.artifacts_dir)
    meta = scorer.metadata
    state.update(
        engine=engine,
        scorer=scorer,
        service=ScoringService(engine, scorer),
        costs=CostConfig(
            meta["costs"]["review_cost"],
            meta["costs"]["friction_cost"],
            int(meta["costs"]["daily_capacity"]),
            meta["costs"]["tolerance"],
        ),
        metrics=json.loads((settings.artifacts_dir / "metrics.json").read_text()),
    )
    ev = settings.artifacts_dir / "eval"
    if (ev / "validation_scores.parquet").exists():
        state["whatif"] = analytics.WhatIf(
            pd.read_parquet(ev / "validation_scores.parquet"), pd.read_parquet(ev / "test_scores.parquet")
        )
    log.info("Modelo %s cargado", scorer.model_version)
    yield
    engine.dispose()


app = FastAPI(
    title="Fraud Detection P2P API",
    version=__version__,
    description="Puntuación de transferencias P2P en tiempo de autorización, cola de alertas, KPI y monitoreo.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health", tags=["sistema"])
def health():
    with state["engine"].connect() as conn:
        conn.execute(sa.text("SELECT 1"))
    return {"status": "ok", "model_version": state["scorer"].model_version}


@app.get("/v1/model", tags=["modelo"])
def model_info():
    m = state["scorer"].metadata
    return {
        k: m[k]
        for k in ("model_version", "trained_at", "features", "partition", "hyperparameters", "costs", "thresholds")
    } | {"test_metrics": state["metrics"]["test"]}


@app.post("/v1/score", response_model=DecisionOut, tags=["puntuación"])
def score(
    tx: TransactionIn,
    persist: bool = Query(True, description="Guardar la operación y su decisión"),
    source: str = Query("simulator", pattern="^(simulator|replay)$"),
):
    return state["service"].score_one(tx, persist, source)


@app.post("/v1/score/batch", response_model=BatchOut, tags=["puntuación"])
def score_batch(batch: BatchIn):
    if not batch.transactions:
        raise HTTPException(422, "El lote está vacío")
    return state["service"].score_batch(batch.transactions, batch.source)


@app.get("/v1/alerts", tags=["operaciones"])
def alerts(
    tier: str = Query("rojo", pattern="^(rojo|ambar)$"),
    status: str = Query("pendiente", pattern="^(pendiente|revisada|todas)$"),
    limit: int = Query(200, le=2_000),
):
    q = (
        sa.select(
            transactions.c.id.label("tx_id"),
            transactions.c.step,
            transactions.c.day,
            transactions.c.hour,
            transactions.c.type,
            transactions.c.amount,
            transactions.c.old_balance_orig,
            transactions.c.name_orig,
            transactions.c.name_dest,
            transactions.c.source,
            decisions.c.score,
            decisions.c.probability,
            decisions.c.reasons,
            decisions.c.contributions,
            decisions.c.dest_ops_prev,
            reviews.c.status,
            reviews.c.reviewed_at,
        )
        .join(decisions, decisions.c.tx_id == transactions.c.id)
        .outerjoin(reviews, reviews.c.tx_id == transactions.c.id)
        .where(decisions.c.tier == tier)
        .order_by(transactions.c.step.desc(), decisions.c.score.desc())
        .limit(limit)
    )
    if status == "pendiente":
        q = q.where(reviews.c.status.is_(None))
    elif status == "revisada":
        q = q.where(reviews.c.status.is_not(None))
    with state["engine"].connect() as conn:
        return [dict(r._mapping) for r in conn.execute(q)]


@app.post("/v1/alerts/{tx_id}/review", tags=["operaciones"])
def review(tx_id: int, body: ReviewIn):
    with state["engine"].begin() as conn:
        if conn.execute(sa.select(decisions.c.tx_id).where(decisions.c.tx_id == tx_id)).first() is None:
            raise HTTPException(404, "Operación inexistente")
        conn.execute(reviews.delete().where(reviews.c.tx_id == tx_id))
        conn.execute(reviews.insert(), [{"tx_id": tx_id, "status": body.status, "analyst": body.analyst}])
    return {"tx_id": tx_id, "status": body.status}


def _traffic():
    return analytics.load_traffic(state["engine"])


@app.get("/v1/kpis/summary", tags=["kpi"])
def kpi_summary():
    return analytics.summary(_traffic(), state["costs"])


@app.get("/v1/kpis/daily", tags=["kpi"])
def kpi_daily():
    return analytics.daily(_traffic(), state["costs"])


@app.get("/v1/kpis/hourly", tags=["kpi"])
def kpi_hourly():
    df = _traffic()
    return {"capacity_per_day": state["costs"].daily_capacity, "rows": analytics.hourly(df) if len(df) else []}


@app.get("/v1/kpis/segments", tags=["kpi"])
def kpi_segments():
    df = _traffic()
    return analytics.segments(df) if len(df) else []


@app.get("/v1/monitoring/drift", tags=["monitoreo"])
def monitoring_drift(window_hours: int = Query(72, ge=24, le=744)):
    return analytics.drift(state["engine"], state["scorer"].metadata["reference"], window_hours)


@app.get("/v1/monitoring/shadow", tags=["monitoreo"])
def monitoring_shadow():
    df = _traffic()
    if not len(df):
        return {"daily": [], "recent_signals": []}
    s = df[df["in_scope"]]
    daily = (
        s.groupby("day")
        .apply(
            lambda g: pd.Series(
                {
                    "champion": g.loc[g["is_red"], "w"].sum(),
                    "challenger": g.loc[g["challenger_alert"], "w"].sum(),
                    "challenger_adv": g.loc[g["challenger_adv_alert"], "w"].sum(),
                    "sentinel": g.loc[g["sentinel_alert"], "w"].sum(),
                    "tactic_signals": g.loc[g["tactic_signal"], "w"].sum(),
                    "tactic_signals_confirmed_fraud": g.loc[g["tactic_signal"] & g["fraud"], "w"].sum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
        .to_dict("records")
    )
    recent = s[s["tactic_signal"]].sort_values("step", ascending=False).head(50)
    return {
        "daily": daily,
        "recent_signals": recent[
            ["id", "step", "type", "amount", "score", "challenger_adv_alert", "sentinel_alert", "fraud"]
        ].to_dict("records"),
    }


@app.get("/v1/economics/whatif", tags=["negocio"])
def whatif(
    review_cost: float = Query(1_500, ge=0),
    friction_cost: float = Query(8_500, ge=0),
    daily_capacity: int = Query(1_000, ge=1, le=100_000),
):
    if "whatif" not in state:
        raise HTTPException(503, "Faltan los puntajes de validación y prueba (artifacts/eval)")
    return state["whatif"].run(CostConfig(review_cost, friction_cost, daily_capacity))


@app.get("/v1/destinations/examples", tags=["puntuación"])
def destination_examples(step: int = Query(400, ge=1), limit: int = Query(8, le=50)):
    """Cuentas de destino con actividad en las 168 h previas al step, para probar el simulador."""
    t = transactions
    q = (
        sa.select(t.c.name_dest, sa.func.count().label("ops"), sa.func.sum(t.c.amount).label("amount"))
        .where(t.c.step >= step - 168, t.c.step < step, t.c.name_dest.like("C%"))
        .group_by(t.c.name_dest)
        .order_by(sa.func.count().desc())
        .limit(limit)
    )
    with state["engine"].connect() as conn:
        return [dict(r._mapping) for r in conn.execute(q)]


@app.delete("/v1/admin/traffic", tags=["sistema"])
def reset_traffic():
    """Borra el tráfico reproducido y simulado; conserva el historial de fondo."""
    with state["engine"].begin() as conn:
        ids = sa.select(transactions.c.id).where(transactions.c.source != "seed")
        conn.execute(reviews.delete().where(reviews.c.tx_id.in_(ids)))
        conn.execute(decisions.delete().where(decisions.c.tx_id.in_(ids)))
        n = conn.execute(transactions.delete().where(transactions.c.source != "seed")).rowcount
    return {"deleted": n}
