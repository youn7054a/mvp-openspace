"""테스트 설정 (Test configuration) — 임시 DB + 콘솔 이메일 폴백."""
from __future__ import annotations

import os
import tempfile

# 앱 import 전에 환경 구성 (Configure env BEFORE importing the app).
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="openspace-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["RESEND_API_KEY"] = ""  # 콘솔 폴백 강제 (force console fallback)
os.environ["ADMIN_PASSWORD"] = "test-admin-pw"
os.environ["BASE_URL"] = "http://testserver"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["UPLOAD_DIR"] = os.path.join(
    tempfile.mkdtemp(prefix="openspace-uploads-"), "uploads"
)

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import routes  # noqa: E402,F401
from app.main import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    """각 테스트 전 테이블 초기화 (Reset tables before each test)."""
    from sqlmodel import SQLModel

    from app import models  # noqa: F401  (테이블 등록 보장)
    from app.database import engine

    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield


@pytest.fixture()
def captured_tokens(monkeypatch):
    """매직링크 토큰 캡처 (Capture issued magic-link tokens)."""
    tokens: list[str] = []

    def fake_send(to_email, token, topic_title):
        tokens.append(token)
        return f"http://testserver/manage/{token}"

    monkeypatch.setattr("app.routes.public.send_magic_link", fake_send)
    return tokens


@pytest.fixture(autouse=True)
def pycon_login(monkeypatch):
    """PyCon 세션 검증을 테스트에서 제어 (Control server-side PyCon verification).

    실제로는 서버가 PyCon 세션 쿠키를 검증하지만, 테스트에서는 요청 헤더
    'X-Test-Email' 을 로그인된 사용자로 간주한다. client 픽스처가 기본값을
    심어두고, 특정 이메일이 필요한 호출은 헤더로 덮어쓴다.
    """
    def fake(request):
        return (request.headers.get("x-test-email") or "").strip() or None

    monkeypatch.setattr("app.routes.public.verified_email", fake)
    monkeypatch.setattr("app.routes.manage.verified_email", fake)


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as c:
        # 기본 로그인 사용자 (default logged-in PyCon user for submissions)
        c.headers.update({"X-Test-Email": "host@example.com"})
        yield c


@pytest.fixture()
def admin_client(client):
    """관리자 로그인된 클라이언트 (Authenticated admin client)."""
    resp = client.post("/admin/login", data={"password": "test-admin-pw"})
    assert resp.status_code == 200
    return client
