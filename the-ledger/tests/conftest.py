import pytest
from fastapi.testclient import TestClient

from app import config, create_app

TEST_FLAG = "GCDxGLORY{pytest_ledger_flag_do_not_ship}"
ADMIN_KEY = "test-admin-key"

ALICE = ("joeharry@helios.bat", "joeharry-helios-1998")
CAROL = ("carol@vantage.example", "carol-vantage-2026")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FLAG", TEST_FLAG)
    monkeypatch.setattr(config, "ADMIN_KEY", ADMIN_KEY)
    return create_app(f"sqlite:///{tmp_path / 'the_ledger.db'}")


@pytest.fixture
def client(app):
    return TestClient(app)


def login(client, credentials):
    email, password = credentials
    resp = client.post("/api/v1/auth", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture
def alice(client):
    return login(client, ALICE)


@pytest.fixture
def carol(client):
    return login(client, CAROL)
