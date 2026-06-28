"""환경 변수 설정 (Environment configuration)."""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """애플리케이션 설정 (Application settings) — 환경 변수에서 로드."""

    def __init__(self) -> None:
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./openspace.db")
        self.resend_api_key: str = os.getenv("RESEND_API_KEY", "").strip()
        self.base_url: str = os.getenv("BASE_URL", "http://localhost:5001").rstrip("/")
        self.admin_password: str = os.getenv("ADMIN_PASSWORD", "change-me")
        self.mail_from: str = os.getenv(
            "MAIL_FROM", "OpenSpace <onboarding@resend.dev>"
        )
        self.session_secret: str = os.getenv(
            "SESSION_SECRET", "dev-insecure-session-secret-change-me"
        )
        # 업로드 이미지 저장 디렉토리 (Uploaded image directory)
        self.upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")

    @property
    def email_enabled(self) -> bool:
        """Resend 키가 있으면 실제 발송, 없으면 콘솔 폴백 (console fallback)."""
        return bool(self.resend_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
