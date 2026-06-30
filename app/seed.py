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

# (제목, 별명, 설명, 이미지 URL) — 별명 빈칸은 '익명'으로 표시
DEMO_TOPICS = [
    ("파이썬 타입 힌트, 어디까지 써봤나요?", "박파이",
     "런타임 검증부터 제네릭·Protocol까지, 실전 경험과 한계를 같이 나눠요.",
     "https://picsum.photos/seed/os1/640/360"),
    ("비동기 디버깅 라이브", "",
     "asyncio가 멈췄을 때 무엇부터 보나요? 다 같이 트러블슈팅.", ""),
    ("러스트 첫 한 달 회고", "김러스트",
     "소유권에 적응한 이야기와 삽질 모음.",
     "https://picsum.photos/seed/os2/640/360"),
    ("작은 팀의 배포 자동화", "데브옵스",
     "GitHub Actions 한 장으로 끝내는 배포 파이프라인.", ""),
    ("LLM 앱 비용 최적화", "프롬프트김",
     "캐싱·모델 선택·토큰 다이어트로 비용을 줄인 사례.",
     "https://picsum.photos/seed/os3/640/360"),
    ("테스트 더블, 무엇을 언제", "",
     "목/스텁/페이크를 언제 쓰고 언제 피하나.", ""),
    ("옵저버빌리티 입문", "관측러",
     "로그·메트릭·트레이스, 어디서부터 시작할까.",
     "https://picsum.photos/seed/os4/640/360"),
    ("오픈소스 첫 기여기", "기여자",
     "첫 PR을 머지하기까지의 과정과 팁.", ""),
    ("모노레포 도입기", "",
     "여러 패키지를 한 저장소에서 관리한 1년.",
     "https://picsum.photos/seed/os5/640/360"),
    ("디자인 시스템 0에서 1", "디자이너정",
     "토큰·컴포넌트·문서화를 처음부터 쌓은 과정.", ""),
    ("코드리뷰 문화 만들기", "리뷰어",
     "리뷰가 싸움이 안 되게 하는 작은 규칙들.",
     "https://picsum.photos/seed/os6/640/360"),
    ("SQLite로 충분한 순간들", "",
     "굳이 Postgres가 필요 없었던 사례들.", ""),
    ("타입스크립트 마이그레이션 후기", "타스러",
     "any를 줄여가며 배운 것들.",
     "https://picsum.photos/seed/os7/640/360"),
    ("온콜, 덜 아프게 하기", "당직왕",
     "알림 피로를 줄이고 잠을 지킨 방법.", ""),
    ("사이드프로젝트 수익화 잔혹사", "",
     "돈을 벌어보려다 배운 현실적인 교훈.",
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

    룸 5개, 타임슬롯 8개(첫 칸은 키노트로 닫힘)를 만들고, 열린 칸(룸×열린 슬롯)을
    모두 채우도록 칸 수만큼 주제를 생성·배정한다(전 세션 가득 채움).
    """
    wipe_all(session)

    # 룸 (Rooms) 5개
    rooms = [Room(name=name, sort_order=i)
             for i, name in enumerate(
                 ["Track A", "Track B", "Track C", "Track D", "Track E"])]
    session.add_all(rooms)
    session.commit()
    for r in rooms:
        session.refresh(r)

    # 타임슬롯 (Timeslots) 8개: 45분 슬롯 + 15분 휴식, 첫 칸은 키노트로 닫음
    base = datetime(2026, 9, 12, 10, 0)
    slots: list[Timeslot] = []
    cursor = base
    for i in range(8):
        end = cursor + timedelta(minutes=45)
        ts = Timeslot(starts_at=cursor, ends_at=end, sort_order=i)
        if i == 0:
            ts.is_closed = True
            ts.label = "키노트 (Keynote)"
        slots.append(ts)
        cursor = end + timedelta(minutes=15)
    session.add_all(slots)
    session.commit()
    for t in slots:
        session.refresh(t)

    # 열린 칸 (open cells) = 열린 슬롯 × 룸 — 이 칸들을 모두 채운다
    open_slots = [t for t in slots if not t.is_closed]
    open_pairs = [(r.id, ts.id) for ts in open_slots for r in rooms]

    # 주제 (Topics): 칸 수만큼 생성. 템플릿을 순환하되 제목 중복은 번호로 구분.
    topics: list[Topic] = []
    for i in range(len(open_pairs)):
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

    # 배정 (Schedule): 모든 열린 칸을 빠짐없이 채운다 (every open cell filled)
    for topic, (room_id, ts_id) in zip(topics, open_pairs):
        session.add(ScheduleEntry(topic_id=topic.id, room_id=room_id,
                                  timeslot_id=ts_id))
    scheduled = len(open_pairs)

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
