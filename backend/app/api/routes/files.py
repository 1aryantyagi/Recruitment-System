"""Signed file-serving route. Access is granted by the signed token only
(pre-signed-URL equivalent — §5.4); no JWT required."""
from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.integrations.storage import local as storage

router = APIRouter(tags=["files"])
log = get_logger("route.files")


@router.get("/files/{token}")
def get_file(token: str):
    try:
        key = storage.resolve_signed(token)
    except ValueError as exc:
        log.warning("route.files.token_invalid", error=str(exc))
        raise NotFoundError("File link invalid or expired", detail=str(exc)) from exc
    if not storage.file_exists(key):
        log.warning("route.files.not_found", key=key)
        raise NotFoundError("File not found")
    content = storage.read_file(key)
    media = "application/pdf" if key.lower().endswith(".pdf") else "application/octet-stream"
    filename = key.split("/")[-1]
    log.info("route.files.served", key=key, media_type=media, bytes=len(content))
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})
