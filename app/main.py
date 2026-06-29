"""애플리케이션 진입점 (Application entry point) — FastHTML 앱 구성."""
from __future__ import annotations

import os

from http.cookies import SimpleCookie

from fasthtml.common import FastHTML, serve
from starlette.staticfiles import StaticFiles

from .config import get_settings
from .auth import note_identity
from .database import init_db
from .i18n import set_lang, set_path
from .routes import admin, manage, public

settings = get_settings()


class LangMiddleware:
    """요청마다 lang 쿠키를 읽어 contextvar 에 세팅 (per-request language).

    순수 ASGI 미들웨어 — 라우트 디스패치와 같은 태스크/컨텍스트 체인에서 실행되어,
    동기 핸들러가 threadpool 로 넘어갈 때 변경된 contextvar 가 복사되어 전파된다.
    (FastHTML 의 before/BaseHTTPMiddleware 는 별도 컨텍스트라 sync 핸들러에 전파 안 됨.)
    헤더 언어 토글의 next 링크용으로 현재 경로(+쿼리)도 함께 저장한다.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            raw_cookie = headers.get(b"cookie", b"").decode("latin-1")
            lang = None
            if raw_cookie:
                jar = SimpleCookie()
                jar.load(raw_cookie)
                if "lang" in jar:
                    lang = jar["lang"].value
            set_lang(lang)
            query = scope.get("query_string", b"").decode("latin-1")
            set_path(scope.get("path", "/") + (f"?{query}" if query else ""))
            # 신원 contextvar 를 요청 시작 시 비운다 — 핸들러가 다시 설정(nav 관리자 탭용).
            note_identity(None)
        await self.app(scope, receive, send)


def create_app() -> FastHTML:
    # 세션 서명 키로 관리자 세션 쿠키 보호 (signed session cookie)
    app = FastHTML(
        secret_key=settings.session_secret,
        title="열린공간 (OpenSpace)",
    )
    app.add_middleware(LangMiddleware)

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
