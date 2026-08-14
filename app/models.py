"""데이터 모델 (Data models) — SQLModel 테이블 정의."""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """타임존 인식 UTC 시각 (Timezone-aware UTC now)."""
    return datetime.now(timezone.utc)


class TopicStatus(str, Enum):
    """주제 상태 (Topic status)."""

    PROPOSED = "proposed"  # 제안됨 (Proposed)


class TopicKind(str, Enum):
    """주제 유형 (Topic kind).

    대화(Conversation)는 룸+시간(셀 하나)에 등록한다. 이벤트(Event)는 시간에만
    등록하고 장소(룸)는 잡지 않는다 — ScheduleEntry.room_id 가 NULL 이다.
    """

    CONVERSATION = "conversation"  # 대화 — 룸+시간
    EVENT = "event"  # 이벤트 — 시간만


class Topic(SQLModel, table=True):
    """토론 주제 (Discussion topic)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str = ""
    host_name: str = ""  # 별명 (Nickname) — 선택 (optional)
    host_email: str  # 비공개 (Never exposed publicly) — 연락·표시용
    # PyCon 회원 id — 소유권 키 (stable owner key). 이메일은 바뀔 수 있어 보조용.
    # 소유권은 신원(PyCon 로그인)으로 확인하므로 매직링크 토큰은 쓰지 않는다.
    host_pycon_id: Optional[int] = Field(default=None, index=True)
    host_username: str = ""  # PyCon username — 기본 별명 후보 (display only)
    image_url: Optional[str] = Field(default=None)  # 주제 대표 이미지 (Topic cover image)
    # 주제 유형 — 등록 시 고정 (대화=룸+시간 / 이벤트=시간만)
    kind: TopicKind = Field(default=TopicKind.CONVERSATION)
    status: TopicStatus = Field(default=TopicStatus.PROPOSED)
    is_hidden: bool = Field(default=False)  # 관리자 숨김 (Admin-hidden)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    deleted_at: Optional[datetime] = Field(default=None)  # 소프트 삭제 (Soft delete)

    @property
    def is_active(self) -> bool:
        """공개 노출 가능 여부 (Visible to the public)."""
        return self.deleted_at is None and not self.is_hidden

    @property
    def is_event(self) -> bool:
        """이벤트 유형 여부 (Event topic — schedules to a time only, no room)."""
        return self.kind == TopicKind.EVENT

    @property
    def display_host(self) -> str:
        """카드에 표시할 제안자 별명 (Nickname for display) — 비면 익명."""
        from .i18n import t

        return self.host_name.strip() or t("익명", "Anonymous")


class Room(SQLModel, table=True):
    """발표 공간 (Room)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RoomSlotClosure(SQLModel, table=True):
    """룸별 닫힌 시간 셀 — 이벤트 중 특정 룸의 대화 접수를 막는다."""

    __table_args__ = (
        UniqueConstraint("room_id", "timeslot_id", name="uq_room_slot_closure"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", index=True)
    timeslot_id: int = Field(foreign_key="timeslot.id", index=True)
    label: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Timeslot(SQLModel, table=True):
    """시간대 (Timeslot)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    starts_at: datetime
    ends_at: datetime
    sort_order: int = Field(default=0)
    is_closed: bool = Field(default=False)  # 닫힌 슬롯 (점심/휴식 등) — 예약 불가
    label: str = Field(default="")  # 표시 라벨 (예: 점심 (Lunch))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def time_label(self) -> str:
        """타임슬롯 시간 라벨 (Time label), 예: 10:00–10:45."""
        return f"{self.starts_at:%H:%M}–{self.ends_at:%H:%M}"

    @property
    def closed_label(self) -> str:
        """닫힌 슬롯에 표시할 문구 (Label for a closed slot)."""
        from .i18n import t

        return self.label.strip() or t("닫힘", "Closed")


class BoardQR(SQLModel, table=True):
    """전광판 QR 코드 (Display-board QR) — 슬롯별 이미지 + 설명.

    행사 안내·설문·후원 링크 등을 전광판에 QR 로 노출한다. 슬롯 번호는 표시 순서이며
    필요한 만큼 추가할 수 있다.
    """

    __table_args__ = (
        # 슬롯당 1개 (one row per slot)
        UniqueConstraint("slot", name="uq_boardqr_slot"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    slot: int = Field(index=True)  # 1 또는 2
    image_url: Optional[str] = Field(default=None)  # QR 이미지 (업로드 또는 URL)
    caption: str = Field(default="")  # QR 설명 (예: 행사 안내, 설문)
    caption_en: str = Field(default="")  # 영어 전광판용 설명
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BoardLanguageSetting(SQLModel, table=True):
    """전광판 한·영 자동 전환 설정 (단일 행, id=1)."""

    id: int = Field(default=1, primary_key=True)
    interval_seconds: int = Field(default=15)
    updated_at: datetime = Field(default_factory=utcnow)


class AutoBoardURL(SQLModel, table=True):
    """자동 전광판에 순서대로 표시할 URL 한 개."""

    id: Optional[int] = Field(default=None, primary_key=True)
    url: str
    label: str = ""
    display_seconds: int = Field(default=30)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class LightningStatus(str, Enum):
    """라이트닝토크 신청 상태 (Lightning talk application status)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class LightningSession(SQLModel, table=True):
    """하루 단위 라이트닝토크 접수·안내 설정."""

    id: Optional[int] = Field(default=None, primary_key=True)
    session_date: date = Field(index=True)
    board_title: str = ""  # 전광판 제목 (날짜별 설정, 비우면 기본 제목)
    starts_at: str = ""  # HH:MM, 정규 세션 종료 후 예정 시각
    venue: str = ""
    venue_en: str = ""  # 영어 신청 화면·전광판용 장소
    description: str = ""
    application_notice: str = ""  # 참가자 신청 화면 안내
    is_open: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class LightningSetting(SQLModel, table=True):
    """라이트닝토크 전체 공통 설정 (단일 행, id=1)."""

    id: int = Field(default=1, primary_key=True)
    application_notice: str = ""
    updated_at: datetime = Field(default_factory=utcnow)


class LightningApplication(SQLModel, table=True):
    """라이트닝토크 신청 — 합격자만 날짜별 발표 순서를 가진다."""

    __table_args__ = (
        UniqueConstraint("session_id", "applicant_pycon_id",
                         name="uq_lightning_session_applicant"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="lightningsession.id", index=True)
    applicant_pycon_id: Optional[int] = Field(default=None, index=True)
    applicant_name: str = ""
    applicant_email: str
    applicant_username: str = ""
    title: str
    description: str = ""
    presentation_url: str = ""
    status: LightningStatus = Field(default=LightningStatus.PENDING, index=True)
    presentation_order: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class LightningQR(SQLModel, table=True):
    """라이트닝토크 안내 전광판 QR 코드."""

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: Optional[int] = Field(default=None, foreign_key="lightningsession.id",
                                      index=True)
    image_url: str
    caption: str = ""
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ScheduleEntry(SQLModel, table=True):
    """타임테이블 배정 (Schedule entry) — 주제·룸·슬롯 매핑."""

    __table_args__ = (
        # 주제당 1슬롯 (one topic -> 0 or 1 slot)
        UniqueConstraint("topic_id", name="uq_schedule_topic"),
        # 슬롯당 1주제 (one room+timeslot -> 0 or 1 topic)
        UniqueConstraint("room_id", "timeslot_id", name="uq_schedule_room_timeslot"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    topic_id: int = Field(foreign_key="topic.id", index=True)
    # 이벤트(시간만 등록)는 room_id 가 NULL. SQLite UNIQUE 는 NULL 을 서로 다른
    # 값으로 보므로 unique(room_id, timeslot_id) 가 한 시간대 여러 이벤트를 허용한다.
    room_id: Optional[int] = Field(default=None, foreign_key="room.id", index=True)
    timeslot_id: int = Field(foreign_key="timeslot.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
