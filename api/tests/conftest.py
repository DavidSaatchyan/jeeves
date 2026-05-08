"""Shared pytest fixtures for API tests."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, get_db
from app.models import Tenant

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(scope="session")
def test_db_engine():
    """Create a SQLite in-memory engine for testing."""
    engine = create_engine("sqlite:///:memory:", pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(test_db_engine):
    """Yield a DB session for each test, with cleanup after."""
    connection = test_db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, autocommit=False)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def tenant(db_session):
    """Create a test tenant."""
    t = Tenant(
        id=uuid.uuid4(),
        name="Test Tenant",
        email=f"test-{uuid.uuid4()}@example.com",
        hashed_password=pwd_ctx.hash("test-password"),
        email_verified=True,
        trial_ends=datetime.utcnow() + timedelta(days=14),
        is_active=True,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def test_env(monkeypatch):
    """Set minimal required env vars for config validation."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-that-is-at-least-32-chars-long")
