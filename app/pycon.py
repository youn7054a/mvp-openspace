"""PyCon 로그인 서버측 검증 (Server-side PyCon session verification).

우리 앱이 *.pycon.kr 하위 도메인으로 배포되면, 브라우저는 도메인이 `.pycon.kr`
인 PyCon 세션 쿠키를 우리 백엔드에도 함께 전송한다. 그 쿠키를 allauth headless
세션 API에 그대로 실어 서버가 직접 호출하면, 인증 여부와 이메일을 **서버가 검증**할
수 있다 — 클라이언트가 보낸 이메일을 신뢰하지 않는다 (진짜 OAuth 토큰 검증에 준함).

브라우저에서 직접 세션을 읽던 방식(JS fetch)과 달리, 여기서 얻은 이메일은
위조할 수 없으므로 주제 소유권 판단의 근거로 쓸 수 있다.
"""
from __future__ import annotations

import httpx

from .components import PYCON_SESSION_URL

# PyCon 세션 API 호출 타임아웃 (초) — 장애 시 빠르게 미인증으로 처리.
_TIMEOUT = 5.0


def verified_email(request) -> str | None:
    """요청에 실린 PyCon 세션 쿠키를 검증해 인증된 이메일을 반환.

    인증되지 않았거나, 쿠키가 없거나, PyCon API 장애 시 None.
    """
    cookie = request.headers.get("cookie")
    if not cookie:
        return None
    try:
        resp = httpx.get(
            PYCON_SESSION_URL,
            headers={"Cookie": cookie, "Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        body = resp.json()
    except (httpx.HTTPError, ValueError):
        return None

    meta = body.get("meta") or {}
    if not meta.get("is_authenticated"):
        return None
    user = (body.get("data") or {}).get("user") or {}
    email = (user.get("email") or "").strip()
    return email or None
