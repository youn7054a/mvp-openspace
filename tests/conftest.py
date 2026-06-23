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


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_client(client):
    """관리자 로그인된 클라이언트 (Authenticated admin client)."""
    resp = client.post("/admin/login", data={"password": "test-admin-pw"})
    assert resp.status_code == 200
    return client
