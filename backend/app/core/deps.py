"""
core/deps.py
────────────
FastAPI dependency functions shared across all routers.
"""

from __future__ import annotations
from typing import Optional, Annotated

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import decode_access_token
from app.core.config import get_settings
from app.db.session import get_db
from app.models.orm import User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


# ── Auth dependency ───────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate JWT and return the authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise credentials_exception

    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise credentials_exception

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Pagination ────────────────────────────────────────────────────

class Pagination:
    def __init__(
        self,
        page: int = 1,
        size: int = 50,
    ):
        if page < 1:
            page = 1
        if size < 1:
            size = 1
        if size > settings.MAX_PAGE_SIZE:
            size = settings.MAX_PAGE_SIZE
        self.page = page
        self.size = size
        self.offset = (page - 1) * size


PaginationDep = Annotated[Pagination, Depends(Pagination)]


# ── DB dependency shorthand ───────────────────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_db)]
