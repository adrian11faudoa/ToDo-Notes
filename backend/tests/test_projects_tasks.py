"""
tests/test_projects_tasks.py
─────────────────────────────
Extended tests for tasks, subtasks, projects, kanban,
today/overdue views, and recurrence.
"""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from tests.conftest import auth_headers


# ── PROJECTS ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_projects_empty(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/projects", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/projects", json={
        "name": "Website Redesign",
        "color": "#9B6DFF",
        "description": "Full site overhaul",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Website Redesign"
    assert data["color"] == "#9B6DFF"
    assert "id" in data


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient):
    headers = await auth_headers(client)
    proj = await client.post("/api/v1/projects", json={"name": "Old Project"}, headers=headers)
    pid = proj.json()["id"]

    resp = await client.patch(f"/api/v1/projects/{pid}", json={
        "name": "Updated Project",
        "color": "#4CAF50",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Project"


@pytest.mark.asyncio
async def test_delete_project_unlinks_tasks(client: AsyncClient):
    headers = await auth_headers(client)
    proj = await client.post("/api/v1/projects", json={"name": "Temp Project"}, headers=headers)
    pid = proj.json()["id"]

    task = await client.post("/api/v1/tasks", json={
        "title": "Project Task", "project_id": pid
    }, headers=headers)
    task_id = task.json()["id"]

    await client.delete(f"/api/v1/projects/{pid}", headers=headers)

    # Task still exists, project_id becomes null
    task_resp = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert task_resp.status_code == 200
    assert task_resp.json()["project_id"] is None


@pytest.mark.asyncio
async def test_project_isolation(client: AsyncClient):
    headers_a = await auth_headers(client)
    headers_b = await auth_headers(
        client, email="b_proj@test.com", password="BProj12345"
    )
    proj = await client.post("/api/v1/projects", json={"name": "A Project"}, headers=headers_a)
    pid = proj.json()["id"]

    resp = await client.patch(f"/api/v1/projects/{pid}", json={"name": "Hijacked"}, headers=headers_b)
    assert resp.status_code == 404


# ── TASKS (extended) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tasks_empty(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/tasks", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "pagination" in data


@pytest.mark.asyncio
async def test_create_task_with_all_fields(client: AsyncClient):
    headers = await auth_headers(client)
    due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    resp = await client.post("/api/v1/tasks", json={
        "title":       "Full task",
        "description": "Detailed description",
        "priority":    1,
        "due_date":    due,
        "tags":        ["urgent", "work"],
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Full task"
    assert data["priority"] == 1
    assert len(data["tags"]) == 2


@pytest.mark.asyncio
async def test_update_task_status(client: AsyncClient):
    headers = await auth_headers(client)
    task = await client.post("/api/v1/tasks", json={"title": "Status Test"}, headers=headers)
    tid = task.json()["id"]

    resp = await client.patch(f"/api/v1/tasks/{tid}", json={"status": "in_progress"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_complete_task_sets_completed_at(client: AsyncClient):
    headers = await auth_headers(client)
    task = await client.post("/api/v1/tasks", json={"title": "Complete me"}, headers=headers)
    tid = task.json()["id"]

    resp = await client.post(f"/api/v1/tasks/{tid}/complete", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_subtasks(client: AsyncClient):
    headers = await auth_headers(client)
    parent = await client.post("/api/v1/tasks", json={"title": "Parent Task"}, headers=headers)
    parent_id = parent.json()["id"]

    # Create subtasks
    for i in range(3):
        await client.post("/api/v1/tasks", json={
            "title":     f"Subtask {i}",
            "parent_id": parent_id,
        }, headers=headers)

    resp = await client.get(f"/api/v1/tasks/{parent_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["subtasks"]) == 3


@pytest.mark.asyncio
async def test_kanban_board(client: AsyncClient):
    headers = await auth_headers(client)
    # Create tasks in different columns
    t1 = await client.post("/api/v1/tasks", json={"title": "Todo task"}, headers=headers)
    t2 = await client.post("/api/v1/tasks", json={"title": "IP task"}, headers=headers)

    await client.post(f"/api/v1/tasks/{t2.json()['id']}/move?column=in_progress", headers=headers)

    resp = await client.get("/api/v1/tasks/kanban", headers=headers)
    assert resp.status_code == 200
    board = resp.json()
    assert "todo" in board
    assert "in_progress" in board
    assert "done" in board
    todo_titles = [t["title"] for t in board["todo"]]
    ip_titles = [t["title"] for t in board["in_progress"]]
    assert "Todo task" in todo_titles
    assert "IP task" in ip_titles


@pytest.mark.asyncio
async def test_today_tasks(client: AsyncClient):
    headers = await auth_headers(client)
    today = datetime.now(timezone.utc).replace(hour=23, minute=59).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

    await client.post("/api/v1/tasks", json={"title": "Today task", "due_date": today}, headers=headers)
    await client.post("/api/v1/tasks", json={"title": "Future task", "due_date": future}, headers=headers)

    resp = await client.get("/api/v1/tasks/today", headers=headers)
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert "Today task" in titles
    assert "Future task" not in titles


@pytest.mark.asyncio
async def test_overdue_tasks(client: AsyncClient):
    headers = await auth_headers(client)
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    await client.post("/api/v1/tasks", json={"title": "Overdue", "due_date": past}, headers=headers)
    await client.post("/api/v1/tasks", json={"title": "Future", "due_date": future}, headers=headers)

    resp = await client.get("/api/v1/tasks/overdue", headers=headers)
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert "Overdue" in titles
    assert "Future" not in titles


@pytest.mark.asyncio
async def test_delete_task(client: AsyncClient):
    headers = await auth_headers(client)
    task = await client.post("/api/v1/tasks", json={"title": "Delete me"}, headers=headers)
    tid = task.json()["id"]

    resp = await client.delete(f"/api/v1/tasks/{tid}", headers=headers)
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/tasks/{tid}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_task_filter_by_project(client: AsyncClient):
    headers = await auth_headers(client)
    proj = await client.post("/api/v1/projects", json={"name": "Filter Proj"}, headers=headers)
    pid = proj.json()["id"]

    await client.post("/api/v1/tasks", json={"title": "In Project", "project_id": pid}, headers=headers)
    await client.post("/api/v1/tasks", json={"title": "No Project"}, headers=headers)

    resp = await client.get(f"/api/v1/tasks?project_id={pid}", headers=headers)
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "In Project"


@pytest.mark.asyncio
async def test_task_isolation(client: AsyncClient):
    headers_a = await auth_headers(client)
    headers_b = await auth_headers(
        client, email="b_task@test.com", password="BTask12345"
    )
    task = await client.post("/api/v1/tasks", json={"title": "A's Task"}, headers=headers_a)
    tid = task.json()["id"]

    resp = await client.get(f"/api/v1/tasks/{tid}", headers=headers_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_kanban_invalid_column(client: AsyncClient):
    headers = await auth_headers(client)
    task = await client.post("/api/v1/tasks", json={"title": "Kanban test"}, headers=headers)
    tid = task.json()["id"]

    resp = await client.post(f"/api/v1/tasks/{tid}/move?column=invalid_column", headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_task_pagination(client: AsyncClient):
    headers = await auth_headers(client)
    for i in range(5):
        await client.post("/api/v1/tasks", json={"title": f"Task {i}"}, headers=headers)

    resp = await client.get("/api/v1/tasks?page=1&size=3", headers=headers)
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["pagination"]["total"] >= 5
    assert data["pagination"]["pages"] >= 2
