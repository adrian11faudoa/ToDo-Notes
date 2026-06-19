"""
tests/conftest.py
─────────────────
Shared pytest fixtures for the NoteFlow API test suite.
Provides: async DB session, test HTTP client with mocked S3.
"""

from __future__ import annotations
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    create_async_engine, async_sessionmaker, AsyncSession
)
from unittest.mock import MagicMock, patch

from app.main import create_app
from app.db.session import get_db
from app.models.orm import Base
from app.services.s3_service import S3Service

# In-memory SQLite — no Postgres required in CI
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession,
        expire_on_commit=False, autoflush=False,
    )
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with DB overridden + S3 mocked."""
    app = create_app()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    mock_s3 = MagicMock(spec=S3Service)
    mock_s3.health_check.return_value = True
    mock_s3.create_presigned_upload.return_value = {
        "upload_url": "http://localhost/upload",
        "s3_key":     "attachments/test/test.png",
        "attachment_id": "test-att-id",
        "expires_in": 300,
    }
    mock_s3.create_presigned_download.return_value = "http://localhost/download/test.png"
    mock_s3.upload_export.return_value = "http://localhost/export/note.pdf"
    mock_s3.delete_attachment.return_value = None
    mock_s3.delete_attachments_batch.return_value = None

    with patch("app.api.routes.notes.s3_service", mock_s3):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


# ── Auth helpers ──────────────────────────────────────────────────

async def register_user(
    client: AsyncClient,
    email: str = "test@noteflow.test",
    password: str = "TestPass123",
    full_name: str = "Test User",
) -> dict:
    """Register a user and return their auth headers."""
    await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": full_name,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": password,
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def auth_headers(client: AsyncClient) -> dict:
    """Shortcut: register default test user and return headers."""
    return await register_user(client)
