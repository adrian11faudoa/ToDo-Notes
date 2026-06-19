"""
tests/test_api.py
──────────────────
Core integration tests: auth and notes endpoints.
Shared fixtures (client, db_session, etc.) live in conftest.py
and are auto-discovered by pytest — no need to import them.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, register_user


# ── Auth tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "new@noteflow.test",
        "password": "NewPass456",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@noteflow.test"
    assert "id" in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient):
    payload = {"email": "dup@test.com", "password": "TestPass123"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "weak@test.com",
        "password": "weakpass",   # no uppercase, no digit
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "login@test.com", "password": "LoginPass789",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@test.com", "password": "LoginPass789",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "wrong@test.com", "password": "RightPass123",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "wrong@test.com", "password": "WrongPass1",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "nobody@test.com", "password": "WhateverPass1",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@noteflow.test"


@pytest.mark.asyncio
async def test_update_me(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.patch("/api/v1/auth/me", json={
        "full_name": "Updated Name",
        "settings": {"theme": "light"},
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"
    assert resp.json()["settings"]["theme"] == "light"


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/auth/change-password", json={
        "current_password": "TestPass123",
        "new_password": "NewSecurePass456",
    }, headers=headers)
    assert resp.status_code == 204

    old_login = await client.post("/api/v1/auth/login", json={
        "email": "test@noteflow.test", "password": "TestPass123",
    })
    assert old_login.status_code == 401

    new_login = await client.post("/api/v1/auth/login", json={
        "email": "test@noteflow.test", "password": "NewSecurePass456",
    })
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_current(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/auth/change-password", json={
        "current_password": "WrongOldPass1",
        "new_password": "NewSecurePass456",
    }, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_refresh_token_flow(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "refresh@test.com", "password": "RefreshPass1",
    })
    login = await client.post("/api/v1/auth/login", json={
        "email": "refresh@test.com", "password": "RefreshPass1",
    })
    refresh_token = login.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token

    old_refresh = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert old_refresh.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "logout@test.com", "password": "LogoutPass1",
    })
    login = await client.post("/api/v1/auth/login", json={
        "email": "logout@test.com", "password": "LogoutPass1",
    })
    refresh_token = login.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 204

    refresh_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_all(client: AsyncClient):
    headers = await register_user(client, email="logoutall@test.com", password="LogoutAll1")
    resp = await client.post("/api/v1/auth/logout-all", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_unauthorized_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/notes")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthorized_invalid_token(client: AsyncClient):
    resp = await client.get("/api/v1/notes", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


# ── Notes tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_note(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/notes", json={
        "title": "My First Note",
        "content": "Hello **world**!",
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My First Note"
    assert data["content"] == "Hello **world**!"
    assert data["word_count"] == 2
    assert "id" in data


@pytest.mark.asyncio
async def test_create_note_defaults(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post("/api/v1/notes", json={}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["title"] == "Untitled Note"


@pytest.mark.asyncio
async def test_list_notes(client: AsyncClient):
    headers = await auth_headers(client)
    for i in range(3):
        await client.post("/api/v1/notes", json={
            "title": f"Note {i}",
            "content": f"Content {i}",
        }, headers=headers)

    resp = await client.get("/api/v1/notes", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["pagination"]["total"] == 3


@pytest.mark.asyncio
async def test_get_note_by_id(client: AsyncClient):
    headers = await auth_headers(client)
    create_resp = await client.post("/api/v1/notes", json={
        "title": "Specific Note", "content": "Find me",
    }, headers=headers)
    note_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/notes/{note_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Specific Note"


@pytest.mark.asyncio
async def test_get_note_not_found(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/notes/nonexistent-id", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_note(client: AsyncClient):
    headers = await auth_headers(client)
    create_resp = await client.post("/api/v1/notes", json={
        "title": "Old Title", "content": "Old content",
    }, headers=headers)
    note_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/v1/notes/{note_id}", json={
        "title": "New Title",
        "content": "Updated content with more words",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Title"
    assert data["word_count"] == 5


@pytest.mark.asyncio
async def test_pin_note(client: AsyncClient):
    headers = await auth_headers(client)
    create_resp = await client.post("/api/v1/notes", json={
        "title": "Pin me", "content": "",
    }, headers=headers)
    note_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/notes/{note_id}/pin?pinned=true", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_pinned"] is True

    unpin = await client.post(f"/api/v1/notes/{note_id}/pin?pinned=false", headers=headers)
    assert unpin.json()["is_pinned"] is False


@pytest.mark.asyncio
async def test_archive_note(client: AsyncClient):
    headers = await auth_headers(client)
    create_resp = await client.post("/api/v1/notes", json={"title": "Archive me"}, headers=headers)
    note_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/notes/{note_id}/archive?archived=true", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_archived"] is True

    list_resp = await client.get("/api/v1/notes", headers=headers)
    ids = [n["id"] for n in list_resp.json()["items"]]
    assert note_id not in ids

    archived_resp = await client.get("/api/v1/notes?archived=true", headers=headers)
    archived_ids = [n["id"] for n in archived_resp.json()["items"]]
    assert note_id in archived_ids


@pytest.mark.asyncio
async def test_soft_delete_note(client: AsyncClient):
    headers = await auth_headers(client)
    create_resp = await client.post("/api/v1/notes", json={"title": "Delete me"}, headers=headers)
    note_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/notes/{note_id}", headers=headers)
    assert del_resp.status_code == 204

    list_resp = await client.get("/api/v1/notes", headers=headers)
    ids = [n["id"] for n in list_resp.json()["items"]]
    assert note_id not in ids

    trash_resp = await client.get("/api/v1/notes/trash", headers=headers)
    trash_ids = [n["id"] for n in trash_resp.json()]
    assert note_id in trash_ids


@pytest.mark.asyncio
async def test_restore_note(client: AsyncClient):
    headers = await auth_headers(client)
    create_resp = await client.post("/api/v1/notes", json={"title": "Restore me"}, headers=headers)
    note_id = create_resp.json()["id"]

    await client.delete(f"/api/v1/notes/{note_id}", headers=headers)
    resp = await client.post(f"/api/v1/notes/{note_id}/restore", headers=headers)
    assert resp.status_code == 200

    list_resp = await client.get("/api/v1/notes", headers=headers)
    ids = [n["id"] for n in list_resp.json()["items"]]
    assert note_id in ids


@pytest.mark.asyncio
async def test_permanent_delete_note(client: AsyncClient):
    headers = await auth_headers(client)
    create_resp = await client.post("/api/v1/notes", json={"title": "Gone forever"}, headers=headers)
    note_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/notes/{note_id}?permanent=true", headers=headers)
    assert resp.status_code == 204

    restore_resp = await client.post(f"/api/v1/notes/{note_id}/restore", headers=headers)
    assert restore_resp.status_code == 404


@pytest.mark.asyncio
async def test_empty_trash(client: AsyncClient):
    headers = await auth_headers(client)
    for i in range(3):
        note = await client.post("/api/v1/notes", json={"title": f"Trash {i}"}, headers=headers)
        await client.delete(f"/api/v1/notes/{note.json()['id']}", headers=headers)

    resp = await client.delete("/api/v1/notes/trash/empty", headers=headers)
    assert resp.status_code == 204

    trash_resp = await client.get("/api/v1/notes/trash", headers=headers)
    assert trash_resp.json() == []


@pytest.mark.asyncio
async def test_search_notes(client: AsyncClient):
    headers = await auth_headers(client)
    await client.post("/api/v1/notes", json={
        "title": "Unique Searchable Title",
        "content": "with distinctive content",
    }, headers=headers)
    await client.post("/api/v1/notes", json={
        "title": "Different note",
        "content": "unrelated text",
    }, headers=headers)

    resp = await client.get("/api/v1/notes/search?q=Searchable", headers=headers)
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_note_isolation_between_users(client: AsyncClient):
    headers_a = await register_user(client, email="usera@test.com", password="UserAPass1")
    headers_b = await register_user(client, email="userb@test.com", password="UserBPass1")

    create_resp = await client.post("/api/v1/notes", json={
        "title": "User A Private", "content": "Secret",
    }, headers=headers_a)
    note_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/notes/{note_id}", headers=headers_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_stats(client: AsyncClient):
    headers = await auth_headers(client)
    await client.post("/api/v1/notes", json={"title": "Note 1", "content": "x"}, headers=headers)
    await client.post("/api/v1/tasks", json={"title": "Task 1"}, headers=headers)

    resp = await client.get("/api/v1/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_notes"] >= 1
    assert data["total_tasks"] >= 1
    assert "completion_rate" in data


# ── Attachments (presigned S3 upload/download) ───────────────────

@pytest.mark.asyncio
async def test_presign_attachment_upload(client: AsyncClient):
    headers = await auth_headers(client)
    note = await client.post("/api/v1/notes", json={"title": "Note with attachment"}, headers=headers)
    note_id = note.json()["id"]

    resp = await client.post(
        f"/api/v1/notes/{note_id}/attachments/presign"
        f"?filename=photo.png&content_type=image/png",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "upload_url" in data
    assert "attachment_id" in data
    assert "s3_key" in data
    assert data["expires_in"] > 0

    # Attachment should now show up on the note (with presigned download URL)
    note_resp = await client.get(f"/api/v1/notes/{note_id}", headers=headers)
    attachments = note_resp.json()["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "photo.png"
    assert attachments[0]["presigned_url"] is not None


@pytest.mark.asyncio
async def test_presign_attachment_note_not_found(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.post(
        "/api/v1/notes/nonexistent-id/attachments/presign?filename=x.png",
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_attachment(client: AsyncClient):
    headers = await auth_headers(client)
    note = await client.post("/api/v1/notes", json={"title": "Note"}, headers=headers)
    note_id = note.json()["id"]

    presign = await client.post(
        f"/api/v1/notes/{note_id}/attachments/presign?filename=doc.pdf",
        headers=headers,
    )
    attachment_id = presign.json()["attachment_id"]

    resp = await client.delete(
        f"/api/v1/notes/{note_id}/attachments/{attachment_id}", headers=headers
    )
    assert resp.status_code == 204

    note_resp = await client.get(f"/api/v1/notes/{note_id}", headers=headers)
    assert note_resp.json()["attachments"] == []


@pytest.mark.asyncio
async def test_delete_attachment_not_found(client: AsyncClient):
    headers = await auth_headers(client)
    note = await client.post("/api/v1/notes", json={"title": "Note"}, headers=headers)
    note_id = note.json()["id"]

    resp = await client.delete(
        f"/api/v1/notes/{note_id}/attachments/nonexistent-id", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_attachment_isolation(client: AsyncClient):
    """User B cannot delete an attachment on User A's note."""
    headers_a = await register_user(client, email="atta@test.com", password="AttaPass1")
    headers_b = await register_user(client, email="attb@test.com", password="AttbPass1")

    note = await client.post("/api/v1/notes", json={"title": "A's Note"}, headers=headers_a)
    note_id = note.json()["id"]
    presign = await client.post(
        f"/api/v1/notes/{note_id}/attachments/presign?filename=secret.png",
        headers=headers_a,
    )
    attachment_id = presign.json()["attachment_id"]

    resp = await client.delete(
        f"/api/v1/notes/{note_id}/attachments/{attachment_id}", headers=headers_b
    )
    assert resp.status_code == 404


# ── Export ────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["txt", "md", "pdf"])
async def test_export_note(client: AsyncClient, fmt: str):
    headers = await auth_headers(client)
    note = await client.post("/api/v1/notes", json={
        "title": "Exportable Note",
        "content": "# Heading\n\nSome **bold** content.",
    }, headers=headers)
    note_id = note.json()["id"]

    resp = await client.get(f"/api/v1/notes/{note_id}/export/{fmt}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "download_url" in data
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_export_invalid_format(client: AsyncClient):
    headers = await auth_headers(client)
    note = await client.post("/api/v1/notes", json={"title": "Note"}, headers=headers)
    note_id = note.json()["id"]

    resp = await client.get(f"/api/v1/notes/{note_id}/export/docx", headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_note_not_found(client: AsyncClient):
    headers = await auth_headers(client)
    resp = await client.get("/api/v1/notes/nonexistent-id/export/txt", headers=headers)
    assert resp.status_code == 404


# ── Tags on notes (explicit add endpoint) ─────────────────────────

@pytest.mark.asyncio
async def test_add_tag_endpoint_directly(client: AsyncClient):
    headers = await auth_headers(client)
    note = await client.post("/api/v1/notes", json={"title": "Taggable"}, headers=headers)
    note_id = note.json()["id"]

    resp = await client.post(f"/api/v1/notes/{note_id}/tags/urgent", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "urgent"
