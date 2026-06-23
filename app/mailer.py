"""매직링크 이메일 발송 (Magic link email) — Resend + 콘솔 폴백."""
from __future__ import annotations

import logging

import httpx

from .config import get_settings

logger = logging.getLogger("openspace.mailer")

RESEND_ENDPOINT = "https://api.resend.com/emails"


def magic_link_url(token: str) -> str:
    """매직링크 전체 URL 생성 (Build the absolute manage URL)."""
    return f"{get_settings().base_url}/manage/{token}"


def send_magic_link(to_email: str, token: str, topic_title: str) -> str:
    """주제 관리 매직링크를 전송하고 URL 을 반환.

    RESEND_API_KEY 가 있으면 Resend 로 발송, 없으면 콘솔/로그로 출력한다.
    어느 경우든 생성된 URL 을 반환해 호출부가 안내 화면에 활용할 수 있다.
    """
    settings = get_settings()
    url = magic_link_url(token)
    subject = f"[Open Space] 주제 관리 링크 (Manage your topic): {topic_title}"
    body_text = (
        f"안녕하세요! (Hello!)\n\n"
        f"제안하신 주제 '{topic_title}' 를 관리하려면 아래 링크를 사용하세요.\n"
        f"Use the private link below to edit, schedule, or cancel your topic.\n\n"
        f"{url}\n\n"
        f"이 링크는 비공개이며 타인과 공유하지 마세요. (Keep this link private.)\n"
    )

    if not settings.email_enabled:
        # 개발 폴백 (Development fallback): 콘솔에 링크 출력
        logger.warning("RESEND_API_KEY 미설정 — 매직링크를 콘솔로 출력합니다.")
        print("\n" + "=" * 70)
        print("📧 [개발 폴백] 매직링크 이메일 (DEV magic-link email, not sent)")
        print(f"   To      : {to_email}")
        print(f"   Subject : {subject}")
        print(f"   Link    : {url}")
        print("=" * 70 + "\n", flush=True)
        return url

    try:
        resp = httpx.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.mail_from,
                "to": [to_email],
                "subject": subject,
                "text": body_text,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        logger.info("매직링크 이메일 발송 완료 -> %s", to_email)
    except Exception:  # pragma: no cover - 네트워크 의존
        logger.exception("매직링크 이메일 발송 실패 (falling back to console).")
        print(f"\n[메일 발송 실패] {to_email} 링크: {url}\n", flush=True)

    return url
