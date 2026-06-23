"""애플리케이션 진입점 (Application entry point) — FastHTML 앱 구성."""
from __future__ import annotations

import os

from fasthtml.common import FastHTML, serve
from starlette.staticfiles import StaticFiles

from .config import get_settings
from .database import init_db
from .routes import admin, manage, public

settings = get_settings()


def create_app() -> FastHTML:
    # 세션 서명 키로 관리자 세션 쿠키 보호 (signed session cookie)
    app = FastHTML(secret_key=settings.session_secret, title="Open Space")

    # 정적 파일 (Static assets): /static/app.css
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # 업로드 이미지 서빙 (Serve uploaded images): /uploads/...
    os.makedirs(settings.upload_dir, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

    # 라우트 등록 (단일 app 에 모듈별 등록 — 순환 import 방지)
    public.register(app)
    manage.register(app)
    admin.register(app)

    init_db()
    return app


app = create_app()


if __name__ == "__main__":
    # uv run python -m app.main
    serve(app="app.main:app", host="0.0.0.0", port=5001, reload=False)
