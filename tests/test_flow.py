"""End-to-end 스모크 테스트 (End-to-end smoke test) — 핵심 사용자 플로우."""
from __future__ import annotations

from sqlmodel import select

from app.database import get_session
from app.models import Room, Timeslot, Topic


def _submit_topic(client, captured_tokens, *, title="테스트 주제 (Test topic)",
                  email="host@example.com"):
    resp = client.post("/topics/new", data={
        "host_name": "홍길동",
        "host_email": email,
        "title": title,
        "description": "설명 (desc)",
    })
    assert resp.status_code == 200
    assert "주제가 등록되었습니다" in resp.text
    assert captured_tokens, "매직링크 토큰이 발급되어야 함"
    return captured_tokens[-1]


def _seed_room_and_slot(admin_client):
    admin_client.post("/admin/rooms", data={"name": "Room A", "sort_order": "0"})
    admin_client.post("/admin/timeslots", data={
        "date": "2026-06-23", "start_time": "10:00",
        "slot_minutes": "45", "break_minutes": "0", "count": "1",
    })
    with get_session() as db:
        room = db.exec(select(Room)).first()
        ts = db.exec(select(Timeslot)).first()
        return room.id, ts.id


def test_bulk_timeslot_generation(admin_client):
    # 한 번에 여러 슬롯 생성 (generate consecutive slots in one request)
    admin_client.post("/admin/timeslots", data={
        "date": "2026-06-23", "start_time": "10:00",
        "slot_minutes": "45", "break_minutes": "10", "count": "4",
    })
    with get_session() as db:
        slots = list(db.exec(select(Timeslot).order_by(Timeslot.sort_order)))
    assert len(slots) == 4
    # 45분 슬롯 + 10분 휴식 → 두 번째 슬롯은 10:55 시작
    assert slots[0].starts_at.strftime("%H:%M") == "10:00"
    assert slots[0].ends_at.strftime("%H:%M") == "10:45"
    assert slots[1].starts_at.strftime("%H:%M") == "10:55"


def test_optional_nickname_and_image_url(client, captured_tokens):
    # 별명 없이 + 이미지 URL 로 제출 (no nickname, with image URL)
    resp = client.post("/topics/new", data={
        "host_email": "img@example.com",
        "host_name": "",
        "title": "이미지 있는 주제",
        "image_url": "https://example.com/cover.png",
    })
    assert resp.status_code == 200
    assert "주제가 등록되었습니다" in resp.text

    # 공개 목록에 이미지와 익명 표시 (image + anonymous host on public list)
    topics = client.get("/topics").text
    assert "https://example.com/cover.png" in topics
    assert "익명 (Anonymous)" in topics


def test_image_upload_stored_and_served(client, captured_tokens):
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)  # 가짜 PNG 헤더 (fake PNG)
    resp = client.post(
        "/topics/new",
        data={"host_email": "up@example.com", "title": "업로드 주제"},
        files={"image_file": ("cover.png", png, "image/png")},
    )
    assert resp.status_code == 200

    from app.models import Topic
    with get_session() as db:
        topic = db.exec(select(Topic).where(Topic.title == "업로드 주제")).first()
    assert topic.image_url and topic.image_url.startswith("/uploads/")
    # 저장된 파일이 서빙되는지 (served back)
    served = client.get(topic.image_url)
    assert served.status_code == 200


def test_reject_non_image_upload(client, captured_tokens):
    resp = client.post(
        "/topics/new",
        data={"host_email": "bad@example.com", "title": "나쁜 파일"},
        files={"image_file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200
    assert "지원하지 않는 이미지 형식" in resp.text


def test_manage_edit_image_add_replace_remove(client, captured_tokens):
    from app.models import Topic

    token = _submit_topic(client, captured_tokens)

    # 관리 페이지에 이미지 편집 UI 노출 (image edit UI present)
    page = client.get(f"/manage/{token}").text
    assert "주제 대표 이미지" in page and 'name="image_file"' in page

    # URL 로 이미지 추가 (add via URL)
    r = client.post(f"/manage/{token}/edit", data={
        "title": "테스트 주제", "image_url": "https://example.com/a.png"})
    assert "저장되었습니다" in r.text
    with get_session() as db:
        assert db.exec(select(Topic)).first().image_url == "https://example.com/a.png"

    # 파일 업로드로 교체 (replace via upload)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    r = client.post(f"/manage/{token}/edit",
                    data={"title": "테스트 주제"},
                    files={"image_file": ("c.png", png, "image/png")})
    with get_session() as db:
        replaced = db.exec(select(Topic)).first().image_url
    assert replaced.startswith("/uploads/")
    assert client.get(replaced).status_code == 200

    # 사진 제거 (remove)
    r = client.post(f"/manage/{token}/edit",
                    data={"title": "테스트 주제", "remove_image": "1"})
    assert "저장되었습니다" in r.text
    with get_session() as db:
        assert db.exec(select(Topic)).first().image_url is None


def test_close_slot_with_custom_label_frees_schedule(client, admin_client, captured_tokens):
    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client, captured_tokens)
    client.post(f"/manage/{token}/schedule", data={"slot": f"{room_id}:{ts_id}"})

    # 커스텀 라벨로 닫기 → 배정 해제 + 라벨 적용 (close with custom label, frees entry)
    admin_client.post(f"/admin/timeslots/{ts_id}/close", data={"label": "키노트"})
    from app.models import ScheduleEntry
    with get_session() as db:
        ts = db.get(Timeslot, ts_id)
        entries = list(db.exec(select(ScheduleEntry).where(
            ScheduleEntry.timeslot_id == ts_id)))
    assert ts.is_closed is True and ts.label == "키노트"
    assert entries == []

    # 닫힌 슬롯은 예약 옵션에 없고, 타임테이블엔 라벨 표시
    assert "Room A · 10:00–10:45" not in client.get(f"/manage/{token}").text
    assert "키노트" in client.get("/schedule").text

    # 라벨 없이 닫으면 기본 라벨 (close without label -> default)
    admin_client.post(f"/admin/timeslots/{ts_id}/close", data={"label": ""})
    with get_session() as db:
        assert db.get(Timeslot, ts_id).label == "닫힘 (Closed)"

    # 다시 열기 (reopen clears label + is_closed)
    admin_client.post(f"/admin/timeslots/{ts_id}/open")
    with get_session() as db:
        ts = db.get(Timeslot, ts_id)
    assert ts.is_closed is False and ts.label == ""
    assert "Room A · 10:00–10:45" in client.get(f"/manage/{token}").text


def test_topic_submission_and_magic_link(client, captured_tokens):
    token = _submit_topic(client, captured_tokens)
    resp = client.get(f"/manage/{token}")
    assert resp.status_code == 200
    assert "내 주제 관리" in resp.text


def test_invalid_magic_link(client):
    resp = client.get("/manage/not-a-real-token")
    assert resp.status_code == 200
    assert "유효하지 않" in resp.text


def test_edit_topic(client, captured_tokens):
    token = _submit_topic(client, captured_tokens)
    resp = client.post(f"/manage/{token}/edit", data={
        "title": "수정된 제목 (Edited)",
        "description": "새 설명",
    })
    assert resp.status_code == 200
    assert "저장되었습니다" in resp.text
    assert "수정된 제목" in resp.text


def test_schedule_register_change_cancel(client, admin_client, captured_tokens):
    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client, captured_tokens)

    # 등록 (register)
    resp = client.post(f"/manage/{token}/schedule",
                       data={"slot": f"{room_id}:{ts_id}"})
    assert resp.status_code == 200
    assert "타임테이블에 등록되었습니다" in resp.text

    # 공개 타임테이블에 노출 (appears on public timetable)
    sched = client.get("/schedule")
    assert "테스트 주제" in sched.text

    # 취소 (cancel)
    resp = client.post(f"/manage/{token}/unschedule")
    assert resp.status_code == 200
    assert "등록이 취소되었습니다" in resp.text


def test_double_booking_prevented(client, admin_client, captured_tokens):
    room_id, ts_id = _seed_room_and_slot(admin_client)
    slot = f"{room_id}:{ts_id}"

    token_a = _submit_topic(client, captured_tokens, title="주제 A", email="a@x.com")
    token_b = _submit_topic(client, captured_tokens, title="주제 B", email="b@x.com")

    r1 = client.post(f"/manage/{token_a}/schedule", data={"slot": slot})
    assert "타임테이블에 등록되었습니다" in r1.text

    # 같은 슬롯에 B 등록 시도 -> 빈 슬롯 목록에 없어 막힘
    r2 = client.post(f"/manage/{token_b}/schedule", data={"slot": slot})
    # DB 유니크 제약으로 거부되어 에러 안내가 떠야 함
    assert ("이미 선택된 슬롯" in r2.text) or ("슬롯 선택이 올바르지 않" in r2.text)

    # 타임테이블에는 B 가 그 슬롯을 차지하지 않음
    sched = client.get("/schedule")
    assert "주제 A" in sched.text


def test_admin_can_schedule_topic(client, admin_client, captured_tokens):
    from app.models import ScheduleEntry

    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client, captured_tokens, title="관리자 배정 주제")
    with get_session() as db:
        topic_id = db.exec(select(Topic).where(Topic.title == "관리자 배정 주제")).first().id

    # 관리자가 슬롯에 배정 (admin assigns to a slot)
    admin_client.post(f"/admin/topics/{topic_id}/schedule",
                      data={"slot": f"{room_id}:{ts_id}"})
    with get_session() as db:
        e = db.exec(select(ScheduleEntry).where(
            ScheduleEntry.topic_id == topic_id)).first()
    assert e is not None and e.room_id == room_id and e.timeslot_id == ts_id
    assert "관리자 배정 주제" in client.get("/schedule").text

    # 관리자가 배정 해제 (admin unassigns)
    admin_client.post(f"/admin/topics/{topic_id}/unschedule")
    with get_session() as db:
        assert db.exec(select(ScheduleEntry).where(
            ScheduleEntry.topic_id == topic_id)).first() is None


def test_admin_schedule_rejects_double_booking(client, admin_client, captured_tokens):
    from app.models import ScheduleEntry

    room_id, ts_id = _seed_room_and_slot(admin_client)
    t1 = _submit_topic(client, captured_tokens, title="주제1", email="a@x.com")
    t2 = _submit_topic(client, captured_tokens, title="주제2", email="b@x.com")
    with get_session() as db:
        id1 = db.exec(select(Topic).where(Topic.title == "주제1")).first().id
        id2 = db.exec(select(Topic).where(Topic.title == "주제2")).first().id

    admin_client.post(f"/admin/topics/{id1}/schedule", data={"slot": f"{room_id}:{ts_id}"})
    r = admin_client.post(f"/admin/topics/{id2}/schedule", data={"slot": f"{room_id}:{ts_id}"})
    assert "이미 사용 중인 슬롯" in r.text
    with get_session() as db:
        assert len(list(db.exec(select(ScheduleEntry)))) == 1  # 두 번째는 거부됨


def test_board_date_selector(client, admin_client):
    # 두 날짜의 타임슬롯 생성 (two days of slots)
    admin_client.post("/admin/timeslots", data={
        "date": "2026-09-12", "start_time": "10:00",
        "slot_minutes": "45", "break_minutes": "0", "count": "1"})
    admin_client.post("/admin/timeslots", data={
        "date": "2026-09-13", "start_time": "14:00",
        "slot_minutes": "45", "break_minutes": "0", "count": "1"})

    # 날짜 탭이 두 개 노출 (both date tabs present)
    board = client.get("/board").text
    assert "09.12" in board and "09.13" in board

    # 9/13 선택 시 그 날 시간만 (14:00), 9/12 시간(10:00)은 안 보임
    d13 = client.get("/board?date=2026-09-13").text
    assert "14:00–14:45" in d13
    assert "10:00–10:45" not in d13


def test_board_renders(client):
    resp = client.get("/board")
    assert resp.status_code == 200
    assert "전광판" in resp.text


def test_board_shows_full_timetable(client, admin_client, captured_tokens):
    # 전광판은 시간과 무관하게 전체 타임테이블의 모든 배정 세션을 카드로 표시
    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client, captured_tokens, title="전광판 카드 세션")
    client.post(f"/manage/{token}/schedule", data={"slot": f"{room_id}:{ts_id}"})

    board = client.get("/board").text
    assert "전광판 카드 세션" in board          # 세션 제목이 카드로 노출
    assert "Room A" in board                     # 트랙(룸) 이름
    assert "10:00–10:45" in board                # 타임슬롯 헤더

    # 닫힌 슬롯(키노트 등)은 라벨 카드로 표시
    admin_client.post(f"/admin/timeslots/{ts_id}/close", data={"label": "키노트"})
    assert "키노트" in client.get("/board").text


def test_seed_demo_data(client, admin_client):
    from app.models import Room, ScheduleEntry, Topic

    resp = admin_client.post("/admin/seed")
    assert resp.status_code == 200
    assert "데모 데이터를 채웠습니다" in resp.text
    with get_session() as db:
        assert len(list(db.exec(select(Room)))) == 5
        assert len(list(db.exec(select(Timeslot)))) == 8
        assert len(list(db.exec(select(Topic)))) == 15
        assert len(list(db.exec(select(ScheduleEntry)))) == 10
        assert any(t.is_closed for t in db.exec(select(Timeslot)))

    # 공개 화면에 데모 데이터가 보임 (demo data visible publicly)
    assert "파이썬 타입 힌트" in client.get("/topics").text
    assert "키노트" in client.get("/schedule").text

    # 전광판: 모든 타임슬롯을 표시 — 배정된 세션 + 빈 슬롯(비어있음) 모두 노출
    board = client.get("/board").text
    assert "파이썬 타입 힌트" in board       # 배정된 세션
    assert "비어있음 (open)" in board         # 빈 슬롯도 보여야 함

    # 다시 시드하면 교체(중복 없음) — 여전히 룸 5개 (re-seed replaces, no dupes)
    admin_client.post("/admin/seed")
    with get_session() as db:
        assert len(list(db.exec(select(Room)))) == 5

    # 전체 비우기 (wipe clears everything)
    admin_client.post("/admin/wipe")
    with get_session() as db:
        assert list(db.exec(select(Topic))) == []
        assert list(db.exec(select(Room))) == []


def test_seed_requires_admin(client):
    # 비로그인 시드 시도 → 로그인으로 리다이렉트, 데이터 변화 없음
    from app.models import Room
    resp = client.post("/admin/seed")
    assert resp.status_code == 200
    assert "관리자 로그인" in resp.text
    with get_session() as db:
        assert list(db.exec(select(Room))) == []


def test_admin_requires_auth(client):
    # 비로그인 상태에서 관리 페이지 -> 로그인으로 리다이렉트
    resp = client.get("/admin/topics")
    assert resp.status_code == 200
    assert "관리자 로그인" in resp.text


def test_admin_hide_topic_removes_from_public(client, admin_client, captured_tokens):
    _submit_topic(client, captured_tokens, title="숨길 주제 (Hide me)")
    # 공개 목록에 노출 확인
    assert "숨길 주제" in client.get("/topics").text

    # 관리자 숨김 처리
    from app.database import get_session as gs
    from app.models import Topic
    with gs() as db:
        tid = db.exec(select(Topic)).first().id
    admin_client.post(f"/admin/topics/{tid}/toggle-hide")

    # 공개 목록에서 사라짐
    assert "숨길 주제" not in client.get("/topics").text
