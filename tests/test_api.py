import numpy as np
import pandas as pd
import pytest

from tests.conftest import DEMO


def _rows(df):
    return [{"step": int(r.step), "type": r.type, "amount": float(r.amount), "old_balance_orig": float(r.oldbalanceOrg),
             "name_dest": r.nameDest, "name_orig": r.nameOrig, "label": int(r.isFraud), "sample_weight": float(r.sample_weight)}
            for r in df.itertuples()]


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_validation_rejects_bad_input(client):
    r = client.post("/v1/score", json={"step": 1, "type": "BITCOIN", "amount": -1, "old_balance_orig": 0, "name_dest": "C1"})
    assert r.status_code == 422


def test_simulator_does_not_persist_by_default_flag(client):
    body = {"step": 400, "type": "TRANSFER", "amount": 181000.0, "old_balance_orig": 181000.0, "name_dest": "C553264065"}
    r = client.post("/v1/score", json=body, params={"persist": False}).json()
    assert r["tier"] == "rojo" and r["tx_id"] is None and r["latency_ms"] > 0


def test_training_serving_parity(client):
    """La API recalcula el historial de 168 h desde la base y debe reproducir el puntaje del entrenamiento."""
    replay = pd.read_parquet(DEMO / "replay.parquet")
    for i in range(0, len(replay), 2500):
        assert client.post("/v1/score/batch", json={"transactions": _rows(replay.iloc[i:i + 2500])}).status_code == 200
    alerts = client.get("/v1/alerts", params={"tier": "rojo", "status": "todas", "limit": 2000}).json()
    got = pd.DataFrame(alerts)[["step", "name_orig", "name_dest", "amount", "score"]]
    exp = replay.rename(columns={"nameOrig": "name_orig", "nameDest": "name_dest"})
    m = got.merge(exp, on=["step", "name_orig", "name_dest", "amount"], how="left")
    assert m["expected_score"].notna().all()
    assert np.abs(m["score"] - m["expected_score"]).max() < 1e-9


def test_kpis_after_replay(client):
    s = client.get("/v1/kpis/summary").json()
    assert s["detected"] >= 0.99 * s["frauds"]
    assert s["false_positives"] == 0
    assert client.get("/v1/kpis/daily").json()[0]["day"] == 16


def test_review_flow(client):
    pending = client.get("/v1/alerts", params={"tier": "rojo", "status": "pendiente", "limit": 1}).json()
    tx_id = pending[0]["tx_id"]
    assert client.post(f"/v1/alerts/{tx_id}/review", json={"status": "fraude_confirmado"}).status_code == 200
    reviewed = client.get("/v1/alerts", params={"tier": "rojo", "status": "revisada"}).json()
    assert any(a["tx_id"] == tx_id for a in reviewed)
    assert client.post("/v1/alerts/999999999/review", json={"status": "liberado"}).status_code == 404


def test_whatif_reproduces_reported_capacity_scenario(client):
    r = client.get("/v1/economics/whatif", params={"daily_capacity": 50}).json()
    assert r["test"]["savings_pct"] == pytest.approx(31.79, abs=0.01)
    assert r["test"]["candidates"] == 1047
    base = client.get("/v1/economics/whatif").json()
    assert base["test"]["tp"] == 4193 and base["test"]["fp"] == 0


def test_drift_report(client):
    rep = client.get("/v1/monitoring/drift").json()
    assert {r["variable"] for r in rep} >= {"log_monto", "__score__"}
