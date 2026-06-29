"""테스트 설정 (Test configuration) — 임시 DB + 콘솔 이메일 폴백."""
from __future__ import annotations

import os
import tempfile

# 앱 import 전에 환경 구성 (Configure env BEFORE importing the app).
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="openspace-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["ADMIN_EMAILS"] = "admin@test.com"  # 관리자 이메일 (이 이메일로 로그인=관리자)
os.environ["BASE_URL"] = "http://testserver"
os.environ["SESSION_SECRET"] = "test-session-secret"
os.environ["DEV_LOGIN_ENABLED"] = "1"  # 테스트에서 수기 로그인(신원) 허용
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
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_client(client):
    """관리자 클라이언트 (Admin) — 참가자 client 와 별개 세션.

    관리자/참가자는 같은 session['identity'] 를 쓰므로, 둘을 동시에 쓰는 테스트를
    위해 admin 은 별도 TestClient(같은 app·DB, 다른 쿠키)로 관리자 이메일 로그인.
    """
    admin = TestClient(client.app)
    r = admin.post("/dev/login", data={"email": "admin@test.com"},
                   follow_redirects=False)
    assert r.status_code == 303
    return admin
