"""데이터 모델 (Data models) — SQLModel 테이블 정의."""
from __future__ import annotations

from datetime import datetime, timezone
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


class Topic(SQLModel, table=True):
    """토론 주제 (Discussion topic)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str = ""
    host_name: str = ""  # 별명 (Nickname) — 선택 (optional)
    host_email: str  # 비공개 (Never exposed publicly)
    image_url: Optional[str] = Field(default=None)  # 주제 대표 이미지 (Topic cover image)
    edit_token_hash: str = Field(index=True)  # 매직링크 토큰 해시만 저장 (hash only)
    edit_token_expires_at: datetime
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
    def display_host(self) -> str:
        """카드에 표시할 제안자 별명 (Nickname for display) — 비면 익명."""
        return self.host_name.strip() or "익명 (Anonymous)"


class Room(SQLModel, table=True):
    """발표 공간 (Room)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    sort_order: int = Field(default=0)
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
        return self.label.strip() or "닫힘 (Closed)"


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
    room_id: int = Field(foreign_key="room.id", index=True)
    timeslot_id: int = Field(foreign_key="timeslot.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
