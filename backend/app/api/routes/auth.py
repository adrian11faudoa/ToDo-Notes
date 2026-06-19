"""
api/routes/auth.py
──────────────────
Authentication endpoints: register, login, refresh, logout, me.
"""

from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Request
from sqlalchemy import select, update

from app.core.deps import CurrentUser, DBSession
from app.core.security import (
    hash_password, verify_password,
    create_access_token, generate_refresh_token,
    store_refresh_token, validate_refresh_token,
    revoke_refresh_token, revoke_all_refresh_tokens,
)
from app.models.orm import User
from app.schemas.schemas import (
    UserRegister, UserLogin, TokenPair, RefreshRequest,
    UserOut, UserUpdate, PasswordChange,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserRegister, db: DBSession):
    """Create a new user account."""
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        settings={
            "theme": "dark", "accent_color": "#4A9EFF",
            "font_size": 14, "startup_page": "notes",
        },
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenPair)
async def login(data: UserLogin, request: Request, db: DBSession):
    """Authenticate and return access + refresh tokens."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)

    access_token, expires_in = create_access_token(user.id, user.email)
    refresh_token = generate_refresh_token()

    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else ""

    await store_refresh_token(db, user.id, refresh_token, user_agent, client_ip)

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(data: RefreshRequest, db: DBSession):
    """Exchange a valid refresh token for a new token pair."""
    rt = await validate_refresh_token(db, data.refresh_token)
    if not rt:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    result = await db.execute(select(User).where(User.id == rt.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate tokens (revoke old, issue new)
    await revoke_refresh_token(db, data.refresh_token)
    access_token, expires_in = create_access_token(user.id, user.email)
    new_refresh = generate_refresh_token()
    await store_refresh_token(db, user.id, new_refresh)

    return TokenPair(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=expires_in,
    )


@router.post("/logout", status_code=204)
async def logout(data: RefreshRequest, db: DBSession):
    """Revoke the provided refresh token."""
    await revoke_refresh_token(db, data.refresh_token)


@router.post("/logout-all", status_code=204)
async def logout_all(current_user: CurrentUser, db: DBSession):
    """Revoke ALL refresh tokens for this user (all devices)."""
    await revoke_all_refresh_tokens(db, current_user.id)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUser):
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(data: UserUpdate, current_user: CurrentUser, db: DBSession):
    if data.full_name is not None:
        current_user.full_name = data.full_name
    if data.settings is not None:
        # Merge — never fully replace settings
        current_user.settings = {**(current_user.settings or {}), **data.settings}
    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.post("/change-password", status_code=204)
async def change_password(
    data: PasswordChange, current_user: CurrentUser, db: DBSession
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(data.new_password)
    await revoke_all_refresh_tokens(db, current_user.id)
