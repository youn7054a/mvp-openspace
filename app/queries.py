"""공용 조회 헬퍼 (Shared query helpers)."""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from .models import BoardQR, Room, ScheduleEntry, Timeslot, Topic

# 전광판 QR 슬롯 (Display-board QR slots) — 고정 2자리
BOARD_QR_SLOTS = (1, 2)

# 참가자 타임테이블 등록이 열리는 시점 (Self-scheduling opens) — 행사 시작 N일 전부터.
# 행사 시작 = 가장 이른 타임슬롯 날짜. 그 전까지는 참가자 자가 등록을 막는다
# (관리자 배정은 예외 — 언제나 가능).
SCHEDULING_LEAD_DAYS = 2


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
    """(room_id, timeslot_id) -> ScheduleEntry 매핑 — 대화(룸 배정)만.

    이벤트(room_id 가 NULL)는 룸 그리드에 들어가지 않으므로 제외한다.
    """
    entries = session.exec(select(ScheduleEntry).where(ScheduleEntry.room_id != None))  # noqa: E711
    return {(e.room_id, e.timeslot_id): e for e in entries}


def events_by_timeslot(session: Session) -> dict[int, list[Topic]]:
    """timeslot_id -> 그 시간대에 등록된 이벤트 주제들 (시간만 등록, 룸 없음).

    room_id 가 NULL 인 ScheduleEntry 를 활성 Topic 과 묶는다. 타임테이블 표·
    전광판에서 룸 칸들 위 배너로 표시할 때 공용으로 쓴다.
    """
    entries = list(session.exec(
        select(ScheduleEntry).where(ScheduleEntry.room_id == None)  # noqa: E711
    ))
    if not entries:
        return {}
    topics = {t.id: t for t in session.exec(select(Topic))}
    out: dict[int, list[Topic]] = {}
    for e in entries:
        tp = topics.get(e.topic_id)
        if tp and tp.is_active:
            out.setdefault(e.timeslot_id, []).append(tp)
    return out


def entry_for_topic(session: Session, topic_id: int) -> ScheduleEntry | None:
    return session.exec(
        select(ScheduleEntry).where(ScheduleEntry.topic_id == topic_id)
    ).first()


def topics_by_id(session: Session) -> dict[int, Topic]:
    return {t.id: t for t in session.exec(select(Topic))}


def topics_for_owner(session: Session, identity) -> list[Topic]:
    """신원의 주제 목록 (My topics) — 소유권 판정은 topic_owned_by 와 동일."""
    rows = list(session.exec(
        select(Topic).where(Topic.deleted_at == None)  # noqa: E711
        .order_by(Topic.created_at.desc())
    ))
    return [tp for tp in rows if topic_owned_by(tp, identity)]


def topic_owned_by(topic: Topic, identity) -> bool:
    """이 주제가 신원의 소유인가 (ownership check) — PyCon 회원 id 기준.

    id 가 있으면 id 로만 판정한다. 이메일 폴백은 host_pycon_id 가 없는 레거시/
    데모 행에만 적용(서로 다른 PyCon 계정이 이메일만 겹쳐도 소유권이 새지 않게).
    """
    if topic is None or topic.deleted_at is not None:
        return False
    if topic.host_pycon_id:  # 소유자 id 가 박힌 주제는 id 로만 판정
        return bool(identity.pycon_id and topic.host_pycon_id == identity.pycon_id)
    # 레거시(소유자 id 없음): 이메일로 보조 매칭
    email = (identity.email or "").strip().lower()
    return bool(email and (topic.host_email or "").strip().lower() == email)


def get_owned_topic(session: Session, topic_id: int, identity) -> Topic | None:
    """id 로 주제를 찾고 신원 소유면 반환, 아니면 None (삭제 제외)."""
    topic = session.get(Topic, topic_id)
    return topic if topic_owned_by(topic, identity) else None


def board_qrs(session: Session) -> dict[int, BoardQR]:
    """전광판 QR 슬롯 매핑 (slot -> BoardQR). 없는 슬롯은 누락."""
    return {q.slot: q for q in session.exec(select(BoardQR))}


def event_start_date(session: Session) -> date | None:
    """행사 시작 날짜 (Event start) = 가장 이른 타임슬롯 날짜. 없으면 None."""
    first = session.exec(
        select(Timeslot).order_by(Timeslot.starts_at).limit(1)
    ).first()
    return first.starts_at.date() if first else None


def scheduling_opens_on(session: Session) -> date | None:
    """참가자 자가 등록이 열리는 날짜 (Self-scheduling open date). 슬롯 없으면 None."""
    start = event_start_date(session)
    return start - timedelta(days=SCHEDULING_LEAD_DAYS) if start else None


def is_scheduling_open(session: Session, *, today: date | None = None) -> bool:
    """지금 참가자 자가 등록이 가능한가 (행사 N일 전부터 True)."""
    opens = scheduling_opens_on(session)
    if opens is None:
        return False
    return (today or date.today()) >= opens
