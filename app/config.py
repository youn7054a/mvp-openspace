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
        self.base_url: str = os.getenv("BASE_URL", "http://localhost:5001").rstrip("/")
        # 관리자 이메일 목록 (Admin emails) — 이 이메일로 로그인하면 관리자 권한.
        # 쉼표로 여러 개 (comma-separated), 대소문자 무시.
        self.admin_emails: set[str] = {
            e.strip().lower()
            for e in os.getenv("ADMIN_EMAILS", "").split(",")
            if e.strip()
        }
        self.session_secret: str = os.getenv(
            "SESSION_SECRET", "dev-insecure-session-secret-change-me"
        )
        # 업로드 이미지 저장 디렉토리 (Uploaded image directory)
        self.upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")
        # 개발용 수기 로그인 허용 (Dev login bypass) — 운영(pycon.kr)에선 미설정.
        self.dev_login_enabled: bool = (
            os.getenv("DEV_LOGIN_ENABLED", "").strip().lower()
            in {"1", "true", "yes", "on"}
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
