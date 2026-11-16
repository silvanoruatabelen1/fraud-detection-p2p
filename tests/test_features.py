import numpy as np
import pandas as pd
import pytest

from fraud_p2p.constants import FEATURES
from fraud_p2p.features import (
    InMemoryHistory,
    Transaction,
    build_features,
    destination_history,
    features_for_transaction,
)


def _one(amount, balance, is_transfer=True, hour=3, ops=0, amt=0.0):
    return build_features(np.array([amount]), np.array([balance]), np.array([is_transfer]),
                          np.array([hour]), np.array([ops]), np.array([amt])).iloc[0]


def test_columns_and_order():
    assert list(build_features(*[np.zeros(2)] * 6).columns) == FEATURES


def test_emptying_signature_is_exact_to_the_cent():
    assert _one(181.0, 181.0)["marca_vaciamiento"] == 1
    assert _one(181.0, 181.01)["marca_vaciamiento"] == 0  # dejar un centavo rompe la firma
    assert _one(0.1 + 0.2, 0.3)["marca_vaciamiento"] == 1  # la comparación es en centavos enteros, no en flotantes


def test_amount_exceeds_balance_and_empty_origin():
    f = _one(500.0, 0.0)
    assert f["monto_excede_saldo"] == 1 and f["emisor_sin_saldo"] == 1
    assert _one(100.0, 50.0)["log_ratio_monto_saldo"] > 0


def test_tranche_10m_requires_sufficient_balance():
    assert _one(10_000_000.0, 12_000_000.0)["tramo_10m_con_saldo"] == 1
    assert _one(10_000_000.0, 9_000_000.0)["tramo_10m_con_saldo"] == 0


def test_hour_is_cyclic():
    a, b = _one(1, 1, hour=0), _one(1, 1, hour=24)
    assert a["hora_sen"] == pytest.approx(b["hora_sen"]) and a["hora_cos"] == pytest.approx(b["hora_cos"])


def test_single_transaction_matches_batch():
    tx = Transaction(step=400, type="TRANSFER", amount=1234.56, old_balance_orig=1234.56, name_dest="C1")
    single = features_for_transaction(tx, 3, 9000.0).iloc[0]
    batch = _one(1234.56, 1234.56, True, 400 % 24, 3, 9000.0)
    pd.testing.assert_series_equal(single, batch, check_names=False)


def _synthetic(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "step": np.sort(rng.integers(1, 400, n)),
        "type": rng.choice(["TRANSFER", "CASH_OUT", "PAYMENT", "CASH_IN"], n),
        "amount": rng.uniform(1, 1e5, n).round(2),
        "nameDest": rng.choice([f"C{i}" for i in range(60)], n),
    })
    df["type"] = df["type"].astype("category")
    return df


def test_history_window_is_causal_and_matches_brute_force():
    df = _synthetic()
    hist = destination_history(df).set_index(["nameDest", "step"])
    for (dest, step), row in hist.sample(200, random_state=1).iterrows():
        prev = df[(df["nameDest"] == dest) & (df["step"] >= step - 168) & (df["step"] < step)]
        assert row["dest_ops_prev"] == len(prev)  # nunca incluye la hora en curso
        assert row["dest_amount_prev"] == pytest.approx(prev["amount"].sum())


def test_online_history_matches_vectorized():
    df = _synthetic(seed=2)
    hist = destination_history(df).set_index(["nameDest", "step"])
    online = InMemoryHistory()
    for step, g in df.groupby("step", sort=True):
        for dest in g["nameDest"].unique():
            if (dest, step) in hist.index:
                ops, amt = online.query(dest, step)
                assert ops == hist.loc[(dest, step), "dest_ops_prev"]
                assert amt == pytest.approx(hist.loc[(dest, step), "dest_amount_prev"])
        for r in g.itertuples():
            online.add(r.nameDest, r.step, r.amount)
