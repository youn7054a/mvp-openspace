"""데이터베이스 엔진 및 세션 (Database engine & session helpers)."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

logger = logging.getLogger(__name__)

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


def _scalar_default_literal(column) -> str | None:
    """모델 컬럼의 상수 기본값을 SQLite DEFAULT 리터럴로 (constant default → SQL literal).

    상수 기본값이 없으면 None (None → no DEFAULT clause). ALTER ADD COLUMN 시 기존
    행을 이 값으로 백필한다(예: host_username '' → 빈 문자열, NULL 아님).
    """
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if isinstance(value, bool):  # bool 은 int 의 하위형이라 먼저 검사
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _ensure_schema() -> None:
    """모델에 새로 생긴 컬럼/인덱스를 기존 테이블에 보강 (lightweight auto-migration).

    SQLModel.create_all 은 없는 *테이블*만 만들고 기존 테이블을 ALTER 하지 않는다.
    그래서 기존 SQLite(운영 볼륨 포함)에 컬럼이 추가되면 'no such column' 으로 깨진다.
    여기서 PRAGMA(=inspector)로 빠진 컬럼만 찾아 ADD COLUMN 으로 보강한다(idempotent).
    SQLite ADD COLUMN 은 UNIQUE/PK 추가는 못 하지만, 우리가 추가하는 컬럼은 모두
    nullable 또는 상수 기본값이라 안전하다.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    dialect = engine.dialect
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # 새 테이블은 create_all 이 이미 만든다
            have = {c["name"] for c in inspector.get_columns(table.name)}
            added = False
            for column in table.columns:
                if column.name in have:
                    continue
                type_sql = column.type.compile(dialect=dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {type_sql}'
                literal = _scalar_default_literal(column)
                if literal is not None:
                    ddl += f" DEFAULT {literal}"
                conn.exec_driver_sql(ddl)
                logger.info("schema: added column %s.%s", table.name, column.name)
                added = True
            if added:
                # 새로 추가된 컬럼의 인덱스(예: host_pycon_id)도 보강
                for index in table.indexes:
                    index.create(bind=conn, checkfirst=True)


def init_db() -> None:
    """테이블 생성 + 컬럼 보강 (Create tables, then patch missing columns) — 앱 시작 시 호출."""
    # models 를 import 해야 메타데이터에 테이블이 등록됨
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_schema()


@contextmanager
def get_session() -> Iterator[Session]:
    """세션 컨텍스트 매니저 (Session context manager)."""
    with Session(engine) as session:
        yield session
