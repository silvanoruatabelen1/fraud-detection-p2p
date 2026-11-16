from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
DEMO = ROOT / "data" / "demo"


@pytest.fixture(scope="session")
def scorer():
    from fraud_p2p.scoring import Scorer

    return Scorer(ARTIFACTS)


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    """API real contra una base temporal (SQLite, o Postgres con TEST_DATABASE_URL) con el historial de demo."""
    import os

    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"
    from api import settings as s

    s.settings.database_url = url
    s.settings.seed_on_startup = True
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c
