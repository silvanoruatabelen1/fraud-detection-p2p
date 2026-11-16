import numpy as np
import pytest

from fraud_p2p.constants import FEATURES
from fraud_p2p.features import Transaction, features_for_transaction


def test_contributions_add_up_to_the_score(scorer):
    tx = Transaction(step=400, type="TRANSFER", amount=181000.0, old_balance_orig=181000.0, name_dest="C1")
    X = features_for_transaction(tx, 0, 0.0)
    s = scorer.score_batch(X)["champion"][0]
    assert scorer.contributions(X).sum() + scorer._intercept == pytest.approx(s, abs=1e-9)


def test_emptying_the_account_is_red(scorer):
    d = scorer.score_transaction(Transaction(400, "TRANSFER", 181000.0, 181000.0, "C1"), 0, 0.0)
    assert d.tier == "rojo" and d.probability > 0.5
    assert any("Vacía la cuenta" in r for r in d.reasons)


def test_typical_cash_out_is_green(scorer):
    d = scorer.score_transaction(Transaction(400, "CASH_OUT", 5000.0, 1200.0, "C2"), 12, 3e6)
    assert d.tier == "verde"


def test_out_of_scope_types_are_approved_without_scoring(scorer):
    for t in ("PAYMENT", "CASH_IN", "DEBIT"):
        d = scorer.score_transaction(Transaction(400, t, 1e6, 1e6, "M1"), 0, 0.0)
        assert not d.in_scope and d.tier == "verde" and d.score is None


def test_tiers_follow_thresholds(scorer):
    assert scorer.tier_for(scorer.red) == "rojo"
    assert scorer.tier_for(np.nextafter(scorer.red, -np.inf)) == "ambar"
    assert scorer.tier_for(scorer.amber - 1) == "verde"


def test_metadata_is_complete(scorer):
    m = scorer.metadata
    assert m["features"] == FEATURES
    assert set(m["artifacts"]) == {"champion", "challenger", "sentinel", "challenger_adv"}
    assert m["thresholds"]["amber"] < m["thresholds"]["red"] < m["thresholds"]["upper_edge"]
