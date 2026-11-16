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
    """API real contra una base SQLite temporal, con el historial de demostración cargado."""
    import os

    db = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    from api import settings as s

    s.settings.database_url = f"sqlite:///{db}"
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c
