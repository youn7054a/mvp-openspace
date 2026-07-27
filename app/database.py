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
    _migrate_topic_kind_and_event_schedule()


def _column_names(conn, table: str) -> dict[str, dict]:
    """테이블 컬럼 메타 (PRAGMA table_info) → {name: row}."""
    from sqlalchemy import text

    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    # row: (cid, name, type, notnull, dflt_value, pk)
    return {r[1]: {"type": r[2], "notnull": r[3], "pk": r[5]} for r in rows}


def _migrate_topic_kind_and_event_schedule() -> None:
    """경량 마이그레이션 (Lightweight migration) — 기존 SQLite DB 보정.

    create_all 은 테이블을 만들 뿐 변경하지 않으므로, 이미 존재하는 DB 에
    1) topic.kind 컬럼을 추가하고,
    2) scheduleentry.room_id 의 NOT NULL 제약을 풀어(이벤트=시간만 등록) 준다.
    테스트는 매번 drop_all/create_all 이라 이 경로를 타지 않는다. idempotent.
    """
    if not settings.database_url.startswith("sqlite"):
        return  # 다른 드라이버는 별도 마이그레이션 도구 사용
    from sqlalchemy import text

    with engine.begin() as conn:
        topic_cols = _column_names(conn, "topic")
        if topic_cols and "kind" not in topic_cols:
            # SQLAlchemy 는 Enum 을 멤버 NAME 으로 저장한다(status='PROPOSED' 과 동일).
            # 따라서 기본값도 값('conversation')이 아니라 이름('CONVERSATION')이어야 한다.
            conn.execute(text(
                "ALTER TABLE topic ADD COLUMN kind VARCHAR "
                "NOT NULL DEFAULT 'CONVERSATION'"
            ))
        # 과거 버전이 소문자 값으로 채운 행 보정 (repair legacy lowercase values).
        if topic_cols:
            conn.execute(text(
                "UPDATE topic SET kind='CONVERSATION' WHERE kind='conversation'"))
            conn.execute(text(
                "UPDATE topic SET kind='EVENT' WHERE kind='event'"))

        sched_cols = _column_names(conn, "scheduleentry")
        # room_id 가 NOT NULL 이면 테이블을 재생성해 nullable 로 전환.
        if sched_cols and sched_cols.get("room_id", {}).get("notnull"):
            # SQLite 는 컬럼 NOT NULL 해제를 직접 못 해 테이블 재생성이 필요.
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text(
                "CREATE TABLE scheduleentry_new ("
                " id INTEGER PRIMARY KEY,"
                " topic_id INTEGER NOT NULL REFERENCES topic(id),"
                " room_id INTEGER REFERENCES room(id),"
                " timeslot_id INTEGER NOT NULL REFERENCES timeslot(id),"
                " created_at DATETIME NOT NULL,"
                " updated_at DATETIME NOT NULL,"
                " CONSTRAINT uq_schedule_topic UNIQUE (topic_id),"
                " CONSTRAINT uq_schedule_room_timeslot UNIQUE (room_id, timeslot_id)"
                ")"
            ))
            conn.execute(text(
                "INSERT INTO scheduleentry_new"
                " (id, topic_id, room_id, timeslot_id, created_at, updated_at)"
                " SELECT id, topic_id, room_id, timeslot_id, created_at, updated_at"
                " FROM scheduleentry"
            ))
            conn.execute(text("DROP TABLE scheduleentry"))
            conn.execute(text(
                "ALTER TABLE scheduleentry_new RENAME TO scheduleentry"))
            # 재생성 후 인덱스 복구 (create_all 이 만든 것과 동일하게)
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scheduleentry_topic_id"
                " ON scheduleentry (topic_id)"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scheduleentry_room_id"
                " ON scheduleentry (room_id)"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scheduleentry_timeslot_id"
                " ON scheduleentry (timeslot_id)"))
            conn.execute(text("PRAGMA foreign_keys=ON"))


@contextmanager
def get_session() -> Iterator[Session]:
    """세션 컨텍스트 매니저 (Session context manager)."""
    with Session(engine) as session:
        yield session
