"""보안 헬퍼 (Security helpers) — 매직링크 토큰 & 관리자 인증."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from .config import get_settings
from .models import utcnow

# 매직링크 유효 기간 (Magic link lifetime)
TOKEN_TTL = timedelta(days=365)


def generate_token() -> tuple[str, str]:
    """원본 토큰과 해시를 생성 (raw token, hash).

    원본은 이메일 링크에만 쓰이고 DB에는 해시만 저장한다.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    """토큰 해시 (SHA-256). 조회 시 동일 함수로 비교."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def token_expiry():
    """새 토큰 만료 시각 (Expiry timestamp for a fresh token)."""
    return utcnow() + TOKEN_TTL


def verify_admin_password(candidate: str) -> bool:
    """관리자 비밀번호 검증 (constant-time compare)."""
    expected = get_settings().admin_password
    return hmac.compare_digest(candidate or "", expected)


# 세션에 저장되는 관리자 플래그 키 (Session key for admin auth)
ADMIN_SESSION_KEY = "is_admin"


def is_admin(session) -> bool:
    """세션에서 관리자 로그인 여부 확인."""
    return bool(session.get(ADMIN_SESSION_KEY))
