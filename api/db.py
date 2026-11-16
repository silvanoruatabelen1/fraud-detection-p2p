"""Esquema operativo. SQLAlchemy Core para que funcione igual en Postgres (compose) y SQLite (tests)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from fraud_p2p.constants import day_of_step

log = logging.getLogger(__name__)
metadata = sa.MetaData()

transactions = sa.Table(
    "transactions", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("step", sa.Integer, nullable=False),
    sa.Column("day", sa.Integer, nullable=False),
    sa.Column("hour", sa.Integer, nullable=False),
    sa.Column("type", sa.String(10), nullable=False),
    sa.Column("amount", sa.Float, nullable=False),
    sa.Column("name_orig", sa.String(20), nullable=False, default=""),
    sa.Column("old_balance_orig", sa.Float, nullable=False),
    sa.Column("name_dest", sa.String(20), nullable=False),
    # seed: historial de fondo; replay: tráfico de prueba reproducido; simulator: carga manual
    sa.Column("source", sa.String(10), nullable=False),
    # Etiqueta conocida después (contracargo o denuncia). Nunca la ve el modelo: solo alimenta los KPI.
    sa.Column("label", sa.SmallInteger, nullable=True),
    sa.Column("sample_weight", sa.Float, nullable=False, default=1.0),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)
sa.Index("ix_tx_dest_step", transactions.c.name_dest, transactions.c.step)
sa.Index("ix_tx_source_day", transactions.c.source, transactions.c.day)

decisions = sa.Table(
    "decisions", metadata,
    sa.Column("tx_id", sa.Integer, sa.ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("model_version", sa.String(40), nullable=False),
    sa.Column("in_scope", sa.Boolean, nullable=False),
    sa.Column("tier", sa.String(6), nullable=False),
    sa.Column("score", sa.Float, nullable=True),
    sa.Column("probability", sa.Float, nullable=True),
    sa.Column("dest_ops_prev", sa.Integer, nullable=False, default=0),
    sa.Column("challenger_alert", sa.Boolean, nullable=False, default=False),
    sa.Column("challenger_adv_alert", sa.Boolean, nullable=False, default=False),
    sa.Column("sentinel_alert", sa.Boolean, nullable=False, default=False),
    sa.Column("tactic_signal", sa.Boolean, nullable=False, default=False),
    sa.Column("reasons", sa.Text, nullable=True),
    sa.Column("features", sa.JSON, nullable=True),
    sa.Column("contributions", sa.JSON, nullable=True),
    sa.Column("latency_ms", sa.Float, nullable=True),
)
sa.Index("ix_dec_tier", decisions.c.tier)

reviews = sa.Table(
    "reviews", metadata,
    sa.Column("tx_id", sa.Integer, sa.ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("status", sa.String(20), nullable=False),  # fraude_confirmado | liberado
    sa.Column("analyst", sa.String(40), nullable=False, default="analista"),
    sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)


def make_engine(url: str) -> sa.Engine:
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return sa.create_engine(url, future=True, **kwargs)


def init_db(engine: sa.Engine) -> None:
    metadata.create_all(engine)


def seed_history(engine: sa.Engine, demo_dir: Path, chunk: int = 20_000) -> int:
    """Carga el historial de fondo si la base está vacía. Idempotente."""
    path = Path(demo_dir) / "history_seed.parquet"
    with engine.begin() as conn:
        already = conn.execute(sa.select(sa.func.count()).select_from(transactions)
                               .where(transactions.c.source == "seed")).scalar_one()
    if already or not path.exists():
        return 0
    df = pd.read_parquet(path)
    rows = pd.DataFrame({
        "step": df["step"].astype(int), "day": day_of_step(df["step"].astype(int)), "hour": df["step"].astype(int) % 24,
        "type": df["type"].astype(str), "amount": df["amount"], "name_orig": df["nameOrig"].astype(str),
        "old_balance_orig": df["oldbalanceOrg"], "name_dest": df["nameDest"].astype(str),
        "source": "seed", "label": None, "sample_weight": 1.0,
    }).to_dict("records")
    with engine.begin() as conn:
        for i in range(0, len(rows), chunk):
            conn.execute(transactions.insert(), rows[i:i + chunk])
    log.info("Historial de fondo cargado: %s operaciones", f"{len(rows):,}")
    return len(rows)
