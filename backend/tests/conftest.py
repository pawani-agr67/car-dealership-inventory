import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        monkeypatch.setenv("DATABASE_PATH", os.path.join(directory, "test.sqlite3"))
        monkeypatch.setenv("JWT_SECRET", "test-only-secret")
        from app.main import app
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def admin(client):
    client.post("/api/auth/register", json={"email": "admin@example.com", "password": "securepass123"})
    # Bootstrap admin exists only in an empty database and is configured by email.
    token = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "securepass123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def buyer(client):
    client.post("/api/auth/register", json={"email": "buyer@example.com", "password": "securepass123"})
    token = client.post("/api/auth/login", json={"email": "buyer@example.com", "password": "securepass123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def vehicle():
    return {"make": "Toyota", "model": "Corolla", "category": "Sedan", "price": 14500, "quantity": 2}
