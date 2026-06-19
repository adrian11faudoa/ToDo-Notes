"""
core/security.py
────────────────
JWT creation/validation, password hashing, refresh token management.
"""

from __future__ import annotations
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.models.orm import User, RefreshToken

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


# ── Passwords ─────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Access token ──────────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    """Raises JWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


# ── Refresh tokens ────────────────────────────────────────────────

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def store_refresh_token(
    db: AsyncSession,
    user_id: str,
    token: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> RefreshToken:
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    rt = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(token),
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(rt)
    await db.flush()
    return rt


async def validate_refresh_token(db: AsyncSession, token: str) -> Optional[RefreshToken]:
    token_hash = hash_refresh_token(token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, token: str):
    rt = await validate_refresh_token(db, token)
    if rt:
        rt.revoked = True
        await db.flush()


async def revoke_all_refresh_tokens(db: AsyncSession, user_id: str):
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
        )
    )
    for rt in result.scalars():
        rt.revoked = True
    await db.flush()
