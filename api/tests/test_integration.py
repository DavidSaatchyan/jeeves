"""Integration tests for core API endpoints using TestClient."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, get_db
from app.main import app
from app.models import Tenant

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture
def client():
    """Create a TestClient with a fresh in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:", pool_pre_ping=True)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = Session(bind=engine, autoflush=False, autocommit=False)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client, db_seed):
    """Return headers with a valid JWT token."""
    response = client.post("/v1/auth/login", json={
        "email": db_seed["email"],
        "password": "test-password",
    })
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture
def db_seed(client):
    """Seed the database with a test tenant."""
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        tenant_id = uuid.uuid4()
        email = f"test-{uuid.uuid4()}@example.com"
        t = Tenant(
            id=tenant_id,
            name="Test Tenant",
            email=email,
            hashed_password=pwd_ctx.hash("test-password"),
            email_verified=True,
            trial_ends=datetime.utcnow() + timedelta(days=14),
            is_active=True,
        )
        db.add(t)
        db.commit()
        return {"tenant_id": tenant_id, "email": email}
    finally:
        db.close()


def test_health(client):
    """Health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_and_login(client):
    """Registration and login flow works."""
    email = f"new-{uuid.uuid4()}@example.com"
    response = client.post("/v1/auth/register", json={
        "tenant_name": "New Tenant",
        "email": email,
        "password": "secure-password-123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

    response = client.post("/v1/auth/login", json={
        "email": email,
        "password": "secure-password-123",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_invalid_credentials(client):
    """Login with wrong password returns 401."""
    response = client.post("/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "wrong",
    })
    assert response.status_code == 401


def test_protected_endpoint_requires_auth(client):
    """Dashboard requires authentication."""
    response = client.get("/v1/dashboard/stats")
    assert response.status_code == 401
