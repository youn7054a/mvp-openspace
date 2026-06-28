"""공용 조회 헬퍼 (Shared query helpers)."""
from __future__ import annotations

from sqlmodel import Session, select

from .models import Room, ScheduleEntry, Timeslot, Topic


def active_topics(session: Session) -> list[Topic]:
    """공개 가능한 주제 목록 (Visible topics) — 삭제/숨김 제외."""
    stmt = (
        select(Topic)
        .where(Topic.deleted_at == None, Topic.is_hidden == False)  # noqa: E711,E712
        .order_by(Topic.created_at.desc())
    )
    return list(session.exec(stmt))


def all_rooms(session: Session) -> list[Room]:
    return list(session.exec(select(Room).order_by(Room.sort_order, Room.id)))


def all_timeslots(session: Session) -> list[Timeslot]:
    # 시간순 우선 정렬 — 칸을 시간대와 무관한 순서로 추가해도 표가 시간순 유지.
    return list(
        session.exec(select(Timeslot).order_by(Timeslot.starts_at, Timeslot.sort_order))
    )


def schedule_map(session: Session) -> dict[tuple[int, int], ScheduleEntry]:
    """(room_id, timeslot_id) -> ScheduleEntry 매핑."""
    entries = session.exec(select(ScheduleEntry))
    return {(e.room_id, e.timeslot_id): e for e in entries}


def entry_for_topic(session: Session, topic_id: int) -> ScheduleEntry | None:
    return session.exec(
        select(ScheduleEntry).where(ScheduleEntry.topic_id == topic_id)
    ).first()


def topics_by_id(session: Session) -> dict[int, Topic]:
    return {t.id: t for t in session.exec(select(Topic))}
