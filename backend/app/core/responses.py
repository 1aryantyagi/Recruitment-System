"""Standard response envelopes (§4.2) and pagination (§4.1)."""
from __future__ import annotations

import math
from typing import Any

from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class Pagination:
    def __init__(self, page: int, limit: int):
        self.page = max(1, page)
        self.limit = min(max(1, limit), MAX_LIMIT)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def pagination_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, description="Page size (clamped to max 100)"),
) -> Pagination:
    # Pagination clamps limit to MAX_LIMIT rather than rejecting (§4.1).
    return Pagination(page, limit)


def single(data: Any) -> dict:
    """Single-object envelope."""
    return {"data": data}


def list_envelope(data: list, total: int, page: int, limit: int) -> dict:
    """List envelope with pagination metadata."""
    total_pages = math.ceil(total / limit) if limit else 0
    return {"data": data, "total": total, "page": page, "limit": limit, "total_pages": total_pages}


def paginate(db: Session, stmt, pagination: Pagination) -> tuple[list, int]:
    """Run a SELECT with LIMIT/OFFSET and a windowed COUNT. Returns (rows, total)."""
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    rows = db.execute(stmt.limit(pagination.limit).offset(pagination.offset)).scalars().all()
    return list(rows), int(total)
