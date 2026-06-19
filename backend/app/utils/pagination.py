"""
utils/pagination.py
───────────────────
Reusable pagination helpers shared across service and route layers.
"""

from __future__ import annotations
import math
from typing import TypeVar, Generic, Sequence
from pydantic import BaseModel

T = TypeVar("T")


class PageMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int
    has_next: bool
    has_prev: bool


class PagedResult(BaseModel, Generic[T]):
    items: Sequence[T]
    pagination: PageMeta


def paginate(
    items: Sequence[T],
    total: int,
    page: int,
    size: int,
) -> PagedResult[T]:
    """Wrap a list of items with pagination metadata."""
    pages = max(1, math.ceil(total / size)) if size else 1
    return PagedResult(
        items=items,
        pagination=PageMeta(
            page=page,
            size=size,
            total=total,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        ),
    )


def offset_from_page(page: int, size: int) -> int:
    """Convert 1-based page number to SQL offset."""
    return (max(1, page) - 1) * size
