"""데이터베이스 엔진 및 세션 (Database engine & session helpers)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()

# SQLite + 멀티스레드 (FastHTML/uvicorn 워커) 허용
connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _record) -> None:
    """SQLite 외래키/유니크 제약 활성화 (Enforce FK constraints on SQLite)."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:  # pragma: no cover - 비 SQLite 드라이버 무시
        pass


def init_db() -> None:
    """테이블 생성 (Create tables) — 앱 시작 시 호출."""
    # models 를 import 해야 메타데이터에 테이블이 등록됨
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """세션 컨텍스트 매니저 (Session context manager)."""
    with Session(engine) as session:
        yield session
