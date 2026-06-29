"""이미지 업로드 처리 (Image upload handling) — 검증·저장·서빙 경로 생성."""
from __future__ import annotations

import logging
import os
import secrets

from .config import get_settings
from .i18n import t

logger = logging.getLogger("openspace.uploads")

# 허용 이미지 형식 (Allowed image types): content-type -> 확장자
_ALLOWED = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
# 최대 업로드 크기 (Max upload size): 5 MiB
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# 공개 서빙 경로 (Public URL prefix) — main.py 의 StaticFiles 마운트와 일치
URL_PREFIX = "/uploads"


class UploadError(Exception):
    """업로드 검증 실패 (Upload validation failed)."""


def _upload_dir() -> str:
    path = get_settings().upload_dir
    os.makedirs(path, exist_ok=True)
    return path


async def save_image(upload) -> str | None:
    """UploadFile 을 검증·저장하고 서빙 URL 을 반환.

    파일이 없으면 None. 형식/크기 위반 시 UploadError.
    파일명은 신뢰하지 않고 무작위 생성 (never trust client filename).
    """
    if upload is None or not getattr(upload, "filename", ""):
        return None

    content_type = (upload.content_type or "").lower().split(";")[0].strip()
    ext = _ALLOWED.get(content_type)
    if ext is None:
        raise UploadError(t(
            "지원하지 않는 이미지 형식입니다. PNG·JPG·GIF·WEBP만 가능합니다.",
            "Unsupported image type — only PNG, JPG, GIF, WEBP are allowed.",
        ))

    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(t(
            "이미지가 너무 큽니다. 5MB 이하만 업로드할 수 있습니다.",
            "Image too large — 5MB max.",
        ))
    if not data:
        return None

    name = f"{secrets.token_urlsafe(16)}{ext}"
    dest = os.path.join(_upload_dir(), name)
    with open(dest, "wb") as fh:
        fh.write(data)
    logger.info("이미지 저장 완료 (saved upload): %s (%d bytes)", name, len(data))
    return f"{URL_PREFIX}/{name}"


def delete_local_image(url: str | None) -> None:
    """로컬 업로드 이미지 파일 삭제 (best-effort) — 외부 URL 은 무시.

    이미지를 교체하거나 제거할 때 디스크에 남은 파일을 정리한다.
    """
    if not url or not url.startswith(URL_PREFIX + "/"):
        return
    name = os.path.basename(url)
    if not name:
        return
    try:
        os.remove(os.path.join(get_settings().upload_dir, name))
    except OSError:
        pass


def normalize_image_url(raw: str | None) -> str | None:
    """붙여넣은 이미지 URL 정규화 (http/https 만 허용)."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    raise UploadError(t(
        "이미지 URL 은 http:// 또는 https:// 로 시작해야 합니다.",
        "Image URL must start with http:// or https://.",
    ))
