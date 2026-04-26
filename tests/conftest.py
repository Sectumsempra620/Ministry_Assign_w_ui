import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    db_path = tmp_path / "test_app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    for module_name in ["main"]:
        sys.modules.pop(module_name, None)

    module = importlib.import_module("main")
    return module


@pytest.fixture
def client(app_module):
    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture
def db_session(app_module):
    db = app_module.SessionLocal()
    try:
        yield db
    finally:
        db.close()
