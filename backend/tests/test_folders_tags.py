"""
tests/test_folders_tags.py
──────────────────────────
Tests for folder and tag CRUD endpoints.
"""

import pytest
from httpx import AsyncClient
from tests.conftest import auth_headers


# ── FOLDERS ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_folders_empty(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/folders", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_folder(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/folders", json={
        "name": "Work Notes",
        "color": "#FF6B6B",
        "icon": "briefcase",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Work Notes"
    assert data["color"] == "#FF6B6B"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_folder_minimal(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/folders", json={"name": "Simple"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["name"] == "Simple"


@pytest.mark.asyncio
async def test_update_folder(client: AsyncClient):
    headers = await auth_headers(client)
    create = await client.post("/api/v1/folders", json={"name": "Old Name"}, headers=headers)
    folder_id = create.json()["id"]

    resp = await client.patch(f"/api/v1/folders/{folder_id}", json={
        "name": "New Name",
        "color": "#4A9EFF",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["color"] == "#4A9EFF"


@pytest.mark.asyncio
async def test_delete_folder(client: AsyncClient):
    headers = await auth_headers(client)
    create = await client.post("/api/v1/folders", json={"name": "To Delete"}, headers=headers)
    folder_id = create.json()["id"]

    resp = await client.delete(f"/api/v1/folders/{folder_id}", headers=headers)
    assert resp.status_code == 204

    # Folder should not appear in list
    list_resp = await client.get("/api/v1/folders", headers=headers)
    ids = [f["id"] for f in list_resp.json()]
    assert folder_id not in ids


@pytest.mark.asyncio
async def test_delete_folder_moves_notes(client: AsyncClient):
    """Deleting a folder should unlink its notes, not delete them."""
    headers = await auth_headers(client)
    folder = await client.post("/api/v1/folders", json={"name": "Temp"}, headers=headers)
    folder_id = folder.json()["id"]

    note = await client.post("/api/v1/notes", json={
        "title": "Orphan Note",
        "folder_id": folder_id,
    }, headers=headers)
    note_id = note.json()["id"]

    await client.delete(f"/api/v1/folders/{folder_id}", headers=headers)

    # Note should still exist, just without a folder
    note_resp = await client.get(f"/api/v1/notes/{note_id}", headers=headers)
    assert note_resp.status_code == 200
    assert note_resp.json()["folder_id"] is None


@pytest.mark.asyncio
async def test_folder_not_found(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.patch("/api/v1/folders/nonexistent-id", json={"name": "X"}, headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_folder_isolation(client: AsyncClient):
    """User A cannot update User B's folder."""
    headers_a = await auth_headers(client)
    headers_b = await auth_headers(
        client, email="b_folders@test.com", password="BPass12345"
    )
    create = await client.post("/api/v1/folders", json={"name": "A's Folder"}, headers=headers_a)
    folder_id = create.json()["id"]

    resp = await client.patch(f"/api/v1/folders/{folder_id}", json={"name": "Hacked"}, headers=headers_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_notes_filtered_by_folder(client: AsyncClient):
    headers = await auth_headers(client)
    folder = await client.post("/api/v1/folders", json={"name": "Filtered"}, headers=headers)
    folder_id = folder.json()["id"]

    # Note in folder
    await client.post("/api/v1/notes", json={
        "title": "In Folder", "folder_id": folder_id
    }, headers=headers)
    # Note not in folder
    await client.post("/api/v1/notes", json={"title": "Outside"}, headers=headers)

    resp = await client.get(f"/api/v1/notes?folder_id={folder_id}", headers=headers)
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "In Folder"


# ── TAGS ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tags_empty(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/tags", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_tag(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/tags", json={
        "name": "important",
        "color": "#FF4444",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "important"
    assert data["color"] == "#FF4444"


@pytest.mark.asyncio
async def test_create_duplicate_tag(client: AsyncClient):
    headers = await auth_headers(client)
    await client.post("/api/v1/tags", json={"name": "unique"}, headers=headers)
    resp = await client.post("/api/v1/tags", json={"name": "unique"}, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_tag(client: AsyncClient):
    headers = await auth_headers(client)
    create = await client.post("/api/v1/tags", json={"name": "deleteme"}, headers=headers)
    tag_id = create.json()["id"]

    resp = await client.delete(f"/api/v1/tags/{tag_id}", headers=headers)
    assert resp.status_code == 204

    tags = await client.get("/api/v1/tags", headers=headers)
    ids = [t["id"] for t in tags.json()]
    assert tag_id not in ids


@pytest.mark.asyncio
async def test_add_tag_to_note(client: AsyncClient):
    headers = await auth_headers(client)
    note = await client.post("/api/v1/notes", json={"title": "Tagged Note"}, headers=headers)
    note_id = note.json()["id"]

    resp = await client.post(f"/api/v1/notes/{note_id}/tags/python", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "python"

    # Tag should appear on the note
    note_resp = await client.get(f"/api/v1/notes/{note_id}", headers=headers)
    tag_names = [t["name"] for t in note_resp.json()["tags"]]
    assert "python" in tag_names


@pytest.mark.asyncio
async def test_remove_tag_from_note(client: AsyncClient):
    headers = await auth_headers(client)
    note = await client.post("/api/v1/notes", json={
        "title": "Note with tag", "tags": ["removeme"]
    }, headers=headers)
    note_id = note.json()["id"]
    note_data = await client.get(f"/api/v1/notes/{note_id}", headers=headers)
    tag_id = note_data.json()["tags"][0]["id"]

    resp = await client.delete(f"/api/v1/notes/{note_id}/tags/{tag_id}", headers=headers)
    assert resp.status_code == 204

    updated = await client.get(f"/api/v1/notes/{note_id}", headers=headers)
    assert len(updated.json()["tags"]) == 0


@pytest.mark.asyncio
async def test_filter_notes_by_tag(client: AsyncClient):
    headers = await auth_headers(client)
    tag = await client.post("/api/v1/tags", json={"name": "filtered-tag"}, headers=headers)
    tag_id = tag.json()["id"]

    note = await client.post("/api/v1/notes", json={
        "title": "Tagged", "tags": ["filtered-tag"]
    }, headers=headers)
    await client.post("/api/v1/notes", json={"title": "Untagged"}, headers=headers)

    resp = await client.get(f"/api/v1/notes?tag_id={tag_id}", headers=headers)
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Tagged"
