import pytest
from fastapi.testclient import TestClient
from data_generator.seed import seed
from backend.main import app


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTEE_DATA_DIR", str(tmp_path))
    seed(users=20, products=100)
    return tmp_path


@pytest.fixture
def client(dataset):
    with TestClient(app) as client:
        yield client
