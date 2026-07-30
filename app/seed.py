"""데모/테스트 데이터 시드 (Demo data seeding) — 룸·타임슬롯·주제·배정 일괄 생성."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, select

from .models import Room, ScheduleEntry, Timeslot, Topic, TopicKind

# (제목, 별명, 설명, 이미지 URL) — 시간에만 등록되는 이벤트 데모
DEMO_EVENTS = [
    ("점심 번개모임 ⚡", "운영팀",
     "점심시간에 로비에서 자유롭게 모여 이야기 나눠요. 룸 없이 진행됩니다.",
     "https://picsum.photos/seed/osev1/640/360"),
    ("보드게임 나이트 🎲", "",
     "행사 끝나고 함께 보드게임 한 판! 장소 무관, 시간만 잡아둔 이벤트예요.",
     None),
]

# (제목, 별명, 설명, 이미지 URL) — 기술에 치우치지 않은 열린공간형 주제 예시.
# 별명 빈칸은 '익명'으로 표시
DEMO_TOPICS = [
    ("파이썬으로 자동화한 귀찮은 일", "자동화냥",
     "반복 업무를 줄인 작은 스크립트와 자동화 아이디어를 나눠요.",
     "https://picsum.photos/seed/os1/640/360"),
    ("내가 좋아하는 동네 산책 코스", "",
     "계절마다 걷기 좋은 길과 그곳에서 발견한 작은 가게를 소개해요.", ""),
    ("Django로 처음 만든 서비스 회고", "장고새싹",
     "처음 배포한 웹서비스에서 배운 점과 다음에 해보고 싶은 것을 이야기해요.",
     "https://picsum.photos/seed/os2/640/360"),
    ("요즘 읽은 책, 한 권만 추천한다면", "책벌레",
     "장르 상관 없이 오래 남은 책과 그 이유를 서로 추천해요.", ""),
    ("파이썬 타입 힌트, 어디까지 써봤나요?", "박파이",
     "런타임 검증부터 제네릭·Protocol까지, 실전 경험과 한계를 같이 나눠요.",
     "https://picsum.photos/seed/os3/640/360"),
    ("집에서 만드는 가장 쉬운 한 끼", "",
     "바쁜 날에도 잘 챙겨 먹는 간단한 레시피와 주방 도구 이야기.", ""),
    ("오픈소스 첫 기여, 어디서 시작할까", "기여자",
     "첫 이슈와 PR을 고르는 법부터 커뮤니티에 질문하는 방법까지 나눠요.",
     "https://picsum.photos/seed/os4/640/360"),
    ("보드게임, 무엇부터 같이 해볼까요?", "게임밤",
     "처음 만난 사람과도 즐기기 좋은 게임을 추천하고 규칙을 배워봐요.", ""),
    ("테스트 코드, 어디까지 작성하나요?", "테스트좋아",
     "테스트가 주는 안심과 유지 비용 사이에서 찾은 나만의 기준을 나눠요.",
     "https://picsum.photos/seed/os5/640/360"),
    ("식물과 함께 사는 법", "초록손",
     "잘 죽지 않는 식물부터 물 주기와 햇빛 자리까지 함께 이야기해요.", ""),
    ("LLM 도구, 일상과 개발에 어떻게 쓰나요?", "프롬프트김",
     "생산성을 높인 활용법과 조심해야 했던 경험을 편하게 나눠요.",
     "https://picsum.photos/seed/os6/640/360"),
    ("좋은 개발 커뮤니티를 만드는 방법", "커뮤니티지기",
     "처음 온 사람도 안전하게 참여하는 모임의 규칙과 문화를 이야기해요.", ""),
    ("파이썬 패키지, 나만의 도구로 만들어보기", "패키저",
     "작은 유틸리티를 패키지로 정리하고 공유하며 배운 점을 나눠요.",
     "https://picsum.photos/seed/os7/640/360"),
    ("새로운 취미를 함께 시작해 볼까요?", "취미수집가",
     "운동·그림·악기·공예 등 처음이라 더 재미있었던 경험과 모임을 이야기해요.",
     "https://picsum.photos/seed/os8/640/360"),
]


def wipe_all(session: Session) -> None:
    """모든 주제·룸·타임슬롯·배정 삭제 (Clear all data)."""
    for model in (ScheduleEntry, Topic, Timeslot, Room):
        for row in session.exec(select(model)):
            session.delete(row)
    session.commit()


def seed_demo(session: Session) -> dict[str, int]:
    """기존 데이터를 비우고 데모 데이터를 채운다 (wipe + seed).

    행사일(2026-08-15, 2026-08-16)별로 오전 키노트·점심 휴식과 1번~7번 테이블의
    40분 진행/20분 휴식 시간표를 만든다. 열린 테이블×시간 칸의 절반만 주제로 채워
    배정 가능한 빈 자리를 함께 보여준다.
    """
    wipe_all(session)

    # 공간 (Rooms): 실제 열린공간 테이블 1번~7번
    rooms = [Room(name=f"{i}번 테이블", sort_order=i - 1) for i in range(1, 8)]
    session.add_all(rooms)
    session.commit()
    for r in rooms:
        session.refresh(r)

    # 타임슬롯 (Timeslots): 양일 오전 키노트 2회, 점심·휴식, 오후 열린공간 4회.
    # 마지막 회차는 16:30–17:10 (입력된 15:10은 40분 진행 규칙에 맞춰 보정).
    slots: list[Timeslot] = []
    for day_index, day in enumerate(((2026, 8, 15), (2026, 8, 16))):
        morning_slots = [
            (datetime(*day, 9, 50), datetime(*day, 10, 30), "키노트 (Keynote)"),
            (datetime(*day, 10, 50), datetime(*day, 11, 30), "키노트 (Keynote)"),
            (datetime(*day, 11, 30), datetime(*day, 13, 30), "점심 및 휴식 (Lunch & Break)"),
        ]
        for slot_index, (starts_at, ends_at, label) in enumerate(morning_slots):
            slots.append(Timeslot(
                starts_at=starts_at,
                ends_at=ends_at,
                sort_order=day_index * 7 + slot_index,
                is_closed=True,
                label=label,
            ))
        cursor = datetime(*day, 13, 30)
        for slot_index in range(4):
            end = cursor + timedelta(minutes=40)
            slots.append(Timeslot(
                starts_at=cursor,
                ends_at=end,
                sort_order=day_index * 7 + 3 + slot_index,
            ))
            cursor = end + timedelta(minutes=20)
    session.add_all(slots)
    session.commit()
    for t in slots:
        session.refresh(t)

    # 열린 칸 (open cells) = 열린 슬롯 × 테이블. 데모에서는 절반만 배정한다.
    open_slots = [t for t in slots if not t.is_closed]
    open_pairs = [(r.id, ts.id) for ts in open_slots for r in rooms]
    scheduled_pairs = open_pairs[::2]

    # 주제 (Topics): 배정할 칸 수만큼 생성. 템플릿을 순환하되 제목 중복은 번호로 구분.
    topics: list[Topic] = []
    for i in range(len(scheduled_pairs)):
        title, nick, desc, img = DEMO_TOPICS[i % len(DEMO_TOPICS)]
        repeat = i // len(DEMO_TOPICS)
        if repeat:  # 두 바퀴째부터는 제목에 번호를 붙여 중복 방지
            title = f"{title} ({repeat + 1})"
        topics.append(Topic(
            title=title, host_name=nick, host_email=f"demo{i}@example.com",
            host_pycon_id=900000 + i,  # 데모 소유자(가상 PyCon id)
            description=desc, image_url=(img or None),
        ))
    session.add_all(topics)
    session.commit()
    for t in topics:
        session.refresh(t)

    # 배정 (Schedule): 열린 칸의 절반만 채워 빈 슬롯도 표시한다.
    for topic, (room_id, ts_id) in zip(topics, scheduled_pairs):
        session.add(ScheduleEntry(topic_id=topic.id, room_id=room_id,
                                  timeslot_id=ts_id))
    scheduled = len(scheduled_pairs)

    # 이벤트(시간만 등록) 데모 — 룸 없이 열린 시간대에 배너로 표시(대화와 공존).
    events: list[Topic] = []
    for i, (title, nick, desc, img) in enumerate(DEMO_EVENTS):
        events.append(Topic(
            title=title, host_name=nick, host_email=f"demoev{i}@example.com",
            host_pycon_id=910000 + i, description=desc,
            image_url=(img or None), kind=TopicKind.EVENT,
        ))
    session.add_all(events)
    session.commit()
    for ev in events:
        session.refresh(ev)
    for ev, ts in zip(events, open_slots):
        # room_id 없이 시간대에만 등록 (event = time-only).
        session.add(ScheduleEntry(topic_id=ev.id, room_id=None, timeslot_id=ts.id))
        scheduled += 1
    session.commit()

    return {"rooms": len(rooms), "timeslots": len(slots),
            "topics": len(topics) + len(events), "scheduled": scheduled}
