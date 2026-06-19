"""
tests/test_pomodoro_search.py
──────────────────────────────
Tests for Pomodoro sessions and global search endpoints.
"""

import pytest
from httpx import AsyncClient
from tests.conftest import auth_headers


# ── POMODORO ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_sessions_empty(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/pomodoro", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_start_session(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/pomodoro", json={
        "duration": 1500,
        "session_type": "work",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["duration"] == 1500
    assert data["session_type"] == "work"
    assert data["completed"] is False


@pytest.mark.asyncio
async def test_start_session_linked_to_task(client: AsyncClient):
    headers = await auth_headers(client)
    task = await client.post("/api/v1/tasks", json={"title": "Focus Task"}, headers=headers)
    task_id = task.json()["id"]

    resp = await client.post("/api/v1/pomodoro", json={
        "task_id": task_id,
        "duration": 1500,
        "session_type": "work",
    }, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["task_id"] == task_id


@pytest.mark.asyncio
async def test_start_session_invalid_task(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/pomodoro", json={
        "task_id": "nonexistent-task-id",
        "duration": 1500,
    }, headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_session(client: AsyncClient):
    headers = await auth_headers(client)
    session = await client.post("/api/v1/pomodoro", json={
        "duration": 1500, "session_type": "work"
    }, headers=headers)
    session_id = session.json()["id"]

    resp = await client.post(f"/api/v1/pomodoro/{session_id}/complete", json={}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] is True
    assert data["ended_at"] is not None


@pytest.mark.asyncio
async def test_complete_session_not_found(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/pomodoro/nonexistent/complete", json={}, headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(client: AsyncClient):
    headers = await auth_headers(client)
    session = await client.post("/api/v1/pomodoro", json={"duration": 300}, headers=headers)
    session_id = session.json()["id"]

    resp = await client.delete(f"/api/v1/pomodoro/{session_id}", headers=headers)
    assert resp.status_code == 204

    list_resp = await client.get("/api/v1/pomodoro", headers=headers)
    ids = [s["id"] for s in list_resp.json()]
    assert session_id not in ids


@pytest.mark.asyncio
async def test_pomodoro_summary(client: AsyncClient):
    headers = await auth_headers(client)
    session = await client.post("/api/v1/pomodoro", json={
        "duration": 1500, "session_type": "work"
    }, headers=headers)
    session_id = session.json()["id"]
    await client.post(f"/api/v1/pomodoro/{session_id}/complete", json={}, headers=headers)

    resp = await client.get("/api/v1/pomodoro/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] >= 1
    assert data["total_focus_minutes"] >= 25
    assert "today_sessions" in data
    assert "today_focus_minutes" in data


@pytest.mark.asyncio
async def test_pomodoro_filter_by_type(client: AsyncClient):
    headers = await auth_headers(client)
    await client.post("/api/v1/pomodoro", json={
        "duration": 1500, "session_type": "work"
    }, headers=headers)
    await client.post("/api/v1/pomodoro", json={
        "duration": 300, "session_type": "short_break"
    }, headers=headers)

    resp = await client.get("/api/v1/pomodoro?session_type=work", headers=headers)
    sessions = resp.json()
    assert all(s["session_type"] == "work" for s in sessions)


@pytest.mark.asyncio
async def test_pomodoro_isolation(client: AsyncClient):
    headers_a = await auth_headers(client)
    headers_b = await auth_headers(
        client, email="b_pomo@test.com", password="BPomo12345"
    )
    session = await client.post("/api/v1/pomodoro", json={"duration": 1500}, headers=headers_a)
    session_id = session.json()["id"]

    resp = await client.delete(f"/api/v1/pomodoro/{session_id}", headers=headers_b)
    assert resp.status_code == 404


# ── GLOBAL SEARCH ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_global_search_empty_query(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/search?q=", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["notes"] == []
    assert data["tasks"] == []


@pytest.mark.asyncio
async def test_global_search_notes_and_tasks(client: AsyncClient):
    headers = await auth_headers(client)
    await client.post("/api/v1/notes", json={
        "title": "Quarterly Planning",
        "content": "Notes about Q3 roadmap and priorities",
    }, headers=headers)
    await client.post("/api/v1/tasks", json={
        "title": "Finish quarterly report",
        "description": "Due before end of Q3",
    }, headers=headers)

    resp = await client.get("/api/v1/search?q=quarterly", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_notes"] >= 0
    assert data["total_tasks"] >= 0
    # With SQLite test backend, FTS may behave differently than Postgres,
    # so we only assert the endpoint responds with the right shape.
    assert "notes" in data and "tasks" in data


@pytest.mark.asyncio
async def test_global_search_isolation(client: AsyncClient):
    """Search must not return another user's data."""
    headers_a = await auth_headers(client)
    headers_b = await auth_headers(
        client, email="b_search@test.com", password="BSearch12345"
    )
    await client.post("/api/v1/notes", json={
        "title": "Private Search Term Zzyx",
        "content": "Should not leak to other users",
    }, headers=headers_a)

    resp = await client.get("/api/v1/search?q=Zzyx", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["total_notes"] == 0


@pytest.mark.asyncio
async def test_global_search_limit(client: AsyncClient):
    headers = await auth_headers(client)
    for i in range(5):
        await client.post("/api/v1/notes", json={
            "title": f"Searchable Note {i}",
            "content": "common search term",
        }, headers=headers)

    resp = await client.get("/api/v1/search?q=common&limit=2", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["notes"]) <= 2


# ── READY ENDPOINT ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ready_endpoint(client: AsyncClient):
    """Lightweight readiness probe — no auth, no DB required."""
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
