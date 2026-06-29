"""End-to-end 스모크 테스트 (End-to-end smoke test) — 핵심 사용자 플로우."""
from __future__ import annotations

from sqlmodel import select

from app.database import get_session
from app.models import BoardQR, Room, Timeslot, Topic


def login(client, email="host@example.com", pycon_id=0):
    """dev 로그인으로 신원 확립 (DEV_LOGIN_ENABLED 필요). 같은 이메일=같은 소유자."""
    r = client.post("/dev/login", data={"email": email, "pycon_id": str(pycon_id)},
                    follow_redirects=False)
    assert r.status_code == 303
    return client


def _submit_topic(client, *, title="테스트 주제 (Test topic)",
                  email="host@example.com", pycon_id=0):
    # 등록은 로그인(신원) 필요 — 소유권은 신원에서 공급. 생성된 주제 id 를 반환.
    login(client, email, pycon_id)
    resp = client.post("/topics/new", data={
        "host_name": "홍길동",
        "title": title,
        "description": "설명 (desc)",
    })
    assert resp.status_code == 200
    assert "주제가 등록되었습니다" in resp.text
    with get_session() as db:
        return db.exec(select(Topic).where(Topic.title == title)
                       .order_by(Topic.id.desc())).first().id


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


def test_optional_nickname_and_image_url(client):
    # 별명 없이 + 이미지 URL 로 제출 (no nickname, with image URL). 이메일은 신원에서.
    login(client, "img@example.com")
    resp = client.post("/topics/new", data={
        "host_name": "",
        "title": "이미지 있는 주제",
        "image_url": "https://example.com/cover.png",
    })
    assert resp.status_code == 200
    assert "주제가 등록되었습니다" in resp.text

    # 공개 목록에 이미지와 익명 표시 (image + anonymous host on public list)
    # 기본 언어는 한국어라 "익명"만 노출(영어 토글 시 Anonymous)
    topics = client.get("/topics").text
    assert "https://example.com/cover.png" in topics
    assert "익명" in topics


def test_image_upload_stored_and_served(client):
    login(client, "up@example.com")
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)  # 가짜 PNG 헤더 (fake PNG)
    resp = client.post(
        "/topics/new",
        data={"title": "업로드 주제"},
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


def test_reject_non_image_upload(client):
    login(client, "bad@example.com")
    resp = client.post(
        "/topics/new",
        data={"title": "나쁜 파일"},
        files={"image_file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200
    assert "지원하지 않는 이미지 형식" in resp.text


def test_manage_edit_image_add_replace_remove(client):
    from app.models import Topic

    token = _submit_topic(client)

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


def test_close_slot_with_custom_label_frees_schedule(client, admin_client):
    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client)
    client.post(f"/schedule/{token}/take", data={"slot": f"{room_id}:{ts_id}"})

    # 커스텀 라벨로 닫기 → 배정 해제 + 라벨 적용 (close with custom label, frees entry)
    admin_client.post(f"/admin/timeslots/{ts_id}/close", data={"label": "키노트"})
    from app.models import ScheduleEntry
    with get_session() as db:
        ts = db.get(Timeslot, ts_id)
        entries = list(db.exec(select(ScheduleEntry).where(
            ScheduleEntry.timeslot_id == ts_id)))
    assert ts.is_closed is True and ts.label == "키노트"
    assert entries == []

    # 닫힌 슬롯은 예약 불가(빈 칸 버튼 없음)이고, 자리 잡기 표엔 라벨 표시
    sched_html = client.get(f"/schedule?topic={token}").text
    assert "이 자리 잡기" not in sched_html and "여기로 이동" not in sched_html
    assert "키노트" in sched_html
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
    # 다시 열면 빈 칸을 눌러 예약 가능 (open cell becomes bookable again)
    reopened = client.get(f"/schedule?topic={token}").text
    assert "이 자리 잡기" in reopened and "10:00–10:45" in reopened


def test_manage_page_opens_for_owner(client):
    tid = _submit_topic(client)
    resp = client.get(f"/manage/{tid}")
    assert resp.status_code == 200
    assert "내 주제 관리" in resp.text


def test_manage_unknown_topic_denied(client):
    # 존재하지 않거나 내 소유 아닌 주제 id → 접근 거부
    login(client, "me@x.com")
    resp = client.get("/manage/999999")
    assert resp.status_code == 200
    assert "권한이 없" in resp.text


def test_edit_topic(client):
    token = _submit_topic(client)
    resp = client.post(f"/manage/{token}/edit", data={
        "title": "수정된 제목 (Edited)",
        "description": "새 설명",
    })
    assert resp.status_code == 200
    assert "저장되었습니다" in resp.text
    assert "수정된 제목" in resp.text


def test_schedule_register_change_cancel(client, admin_client):
    from app.models import ScheduleEntry

    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client)

    # 등록 (register) — 타임테이블 뷰에서 자리 잡기
    resp = client.post(f"/schedule/{token}/take",
                       data={"slot": f"{room_id}:{ts_id}"})
    assert resp.status_code == 200
    assert "✓ 테스트 주제" in resp.text             # 내 자리에 ✓+제목 표시
    with get_session() as db:
        assert db.exec(select(ScheduleEntry)).first() is not None

    # 공개 타임테이블에 노출 (비소유자=admin은 읽기전용 표에 제목 노출)
    assert "테스트 주제" in admin_client.get("/schedule").text

    # 취소 (cancel)
    resp = client.post(f"/schedule/{token}/cancel")
    assert resp.status_code == 200
    with get_session() as db:
        assert db.exec(select(ScheduleEntry)).first() is None


def test_scheduling_locked_until_two_days_before(client, admin_client):
    # 행사가 한참 뒤면 참가자 자가 등록이 아직 안 열려 막힌다 (2일 전부터 오픈)
    admin_client.post("/admin/rooms", data={"name": "Room A", "sort_order": "0"})
    admin_client.post("/admin/timeslots", data={
        "date": "2026-12-25", "start_time": "10:00",
        "slot_minutes": "45", "break_minutes": "0", "count": "1"})
    with get_session() as db:
        room_id = db.exec(select(Room)).first().id
        ts_id = db.exec(select(Timeslot)).first().id
    token = _submit_topic(client)

    # 타임테이블(자리 잡기): 등록 버튼 없이 '행사 이틀 전' 안내만 노출
    page = client.get(f"/schedule?topic={token}").text
    assert "행사 이틀 전" in page
    assert "2026-12-23" in page          # 등록 시작일(행사 2일 전)
    assert "이 자리 잡기" not in page      # 빈 칸 등록 버튼 숨김

    # 직접 등록 POST 도 막힘 + 엔트리 미생성
    from app.models import ScheduleEntry
    r = client.post(f"/schedule/{token}/take", data={"slot": f"{room_id}:{ts_id}"})
    assert "행사 이틀 전" in r.text
    with get_session() as db:
        assert db.exec(select(ScheduleEntry)).first() is None

    # 관리자는 윈도우와 무관하게 배정 가능 (admin override, PRD)
    with get_session() as db:
        tid = db.exec(select(Topic)).first().id
    admin_client.post(f"/admin/topics/{tid}/schedule", data={"slot": f"{room_id}:{ts_id}"})
    with get_session() as db:
        assert db.exec(select(ScheduleEntry)).first() is not None


def test_double_booking_prevented(client, admin_client):
    room_id, ts_id = _seed_room_and_slot(admin_client)
    slot = f"{room_id}:{ts_id}"

    # A 가 자기 주제를 슬롯에 등록(로그인=소유자). _submit_topic 이 로그인 상태로 둠.
    id_a = _submit_topic(client, title="주제 A", email="a@x.com")
    r1 = client.post(f"/schedule/{id_a}/take", data={"slot": slot})
    assert "✓ 주제 A" in r1.text

    # B 가 자기 주제를 같은 슬롯에 시도 → DB 유니크 제약으로 거부
    id_b = _submit_topic(client, title="주제 B", email="b@x.com")  # 이제 B 로 로그인
    r2 = client.post(f"/schedule/{id_b}/take", data={"slot": slot})
    assert ("이미 선택된 슬롯" in r2.text) or ("슬롯 선택이 올바르지 않" in r2.text)

    # 공개(비로그인) 타임테이블에는 A 가 그 슬롯을 차지(읽기 전용 표에 제목 노출)
    client.post("/logout")
    assert "주제 A" in client.get("/schedule").text


def test_admin_can_schedule_topic(client, admin_client):
    from app.models import ScheduleEntry

    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client, title="관리자 배정 주제")
    with get_session() as db:
        topic_id = db.exec(select(Topic).where(Topic.title == "관리자 배정 주제")).first().id

    # 관리자가 슬롯에 배정 (admin assigns to a slot)
    admin_client.post(f"/admin/topics/{topic_id}/schedule",
                      data={"slot": f"{room_id}:{ts_id}"})
    with get_session() as db:
        e = db.exec(select(ScheduleEntry).where(
            ScheduleEntry.topic_id == topic_id)).first()
    assert e is not None and e.room_id == room_id and e.timeslot_id == ts_id
    # 비소유자(admin, 자기 주제 없음) 읽기전용 표에 제목 노출
    assert "관리자 배정 주제" in admin_client.get("/schedule").text

    # 관리자가 배정 해제 (admin unassigns)
    admin_client.post(f"/admin/topics/{topic_id}/unschedule")
    with get_session() as db:
        assert db.exec(select(ScheduleEntry).where(
            ScheduleEntry.topic_id == topic_id)).first() is None


def test_admin_schedule_rejects_double_booking(client, admin_client):
    from app.models import ScheduleEntry

    room_id, ts_id = _seed_room_and_slot(admin_client)
    t1 = _submit_topic(client, title="주제1", email="a@x.com")
    t2 = _submit_topic(client, title="주제2", email="b@x.com")
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


def test_schedule_topic_interactive_grid_register(client, admin_client):
    # 타임테이블 뷰(?topic=): 빈 칸을 눌러(=take POST) 등록되는 흐름
    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client)

    page = client.get(f"/schedule?topic={token}").text
    assert "Room A" in page and "10:00–10:45" in page  # 표에 룸/시간 노출
    assert "이 자리 잡기" in page                        # 빈 칸 등록 버튼

    # 빈 칸 버튼이 호출하는 엔드포인트로 등록 (button posts slot=room:ts)
    r = client.post(f"/schedule/{token}/take",
                    data={"slot": f"{room_id}:{ts_id}"})
    assert "✓ 테스트 주제" in r.text and "여기로 이동" not in r.text  # 내 자리(✓+제목), 다른 빈칸 없음


def test_schedule_topic_multiday_date_tabs(client, admin_client):
    # 행사가 여러 날이면 자리 잡기 표에도 날짜 탭이 노출된다
    admin_client.post("/admin/rooms", data={"name": "Room A", "sort_order": "0"})
    admin_client.post("/admin/timeslots", data={
        "date": "2026-09-12", "start_time": "10:00",
        "slot_minutes": "45", "break_minutes": "0", "count": "1"})
    admin_client.post("/admin/timeslots", data={
        "date": "2026-09-13", "start_time": "14:00",
        "slot_minutes": "45", "break_minutes": "0", "count": "1"})
    token = _submit_topic(client)

    page = client.get(f"/schedule?topic={token}").text
    assert "date-tabs" in page                         # 날짜 탭 영역 존재
    assert "09.12" in page and "09.13" in page         # 두 날짜 탭
    assert "10:00–10:45" in page and "14:00–14:45" in page  # 두 날 슬롯 모두 렌더
    # 각 표 위에 어떤 날 표인지 날짜 제목 캡션 표시
    assert "2026년 9월 12일" in page and "2026년 9월 13일" in page
    assert "타임테이블" in page


def test_tt_add_row_creates_default_room_and_slot(admin_client):
    # 워드 표 빌더: 첫 '시간(행) 추가' 시 기본 방 1개 + 슬롯 1개 자동 생성
    r = admin_client.post("/admin/timetable/add-row")
    assert r.status_code == 200 and "tt-builder" in r.text
    with get_session() as db:
        rooms = list(db.exec(select(Room)))
        tss = list(db.exec(select(Timeslot)))
    assert [x.name for x in rooms] == ["룸 1"]
    assert len(tss) == 1
    assert tss[0].starts_at.strftime("%H:%M") == "10:00"
    assert tss[0].ends_at.strftime("%H:%M") == "10:45"


def test_tt_add_room_and_row_continuation(admin_client):
    # 옆 ＋는 방(열) 추가, 아래 ＋ 행은 직전 슬롯에 이어 같은 길이로 연속 생성
    admin_client.post("/admin/timetable/add-row")     # 룸1 + 10:00–10:45
    admin_client.post("/admin/timetable/add-room")    # 룸2 추가
    admin_client.post("/admin/timetable/add-row")     # 10:45–11:30
    with get_session() as db:
        rooms = [r.name for r in db.exec(select(Room))]
        tss = sorted(db.exec(select(Timeslot)), key=lambda t: t.starts_at)
    assert rooms == ["룸 1", "룸 2"]
    assert [f"{t.starts_at:%H:%M}-{t.ends_at:%H:%M}" for t in tss] == \
        ["10:00-10:45", "10:45-11:30"]


def test_tt_edit_time_and_rename_room(admin_client):
    admin_client.post("/admin/timetable/add-row")
    with get_session() as db:
        sid = db.exec(select(Timeslot)).first().id
        rid = db.exec(select(Room)).first().id
    admin_client.post(f"/admin/timetable/slot/{sid}/time",
                      data={"start_time": "09:30", "end_time": "10:15"})
    admin_client.post(f"/admin/timetable/room/{rid}/rename",
                      data={"name": "메인홀"})
    with get_session() as db:
        ts = db.get(Timeslot, sid)
        assert f"{ts.starts_at:%H:%M}-{ts.ends_at:%H:%M}" == "09:30-10:15"
        assert db.get(Room, rid).name == "메인홀"
    # 잘못된 시간(종료 ≤ 시작)은 무시되고 기존 값 유지
    admin_client.post(f"/admin/timetable/slot/{sid}/time",
                      data={"start_time": "11:00", "end_time": "10:00"})
    with get_session() as db:
        ts = db.get(Timeslot, sid)
        assert f"{ts.starts_at:%H:%M}-{ts.ends_at:%H:%M}" == "09:30-10:15"


def test_tt_delete_row_and_column(admin_client):
    admin_client.post("/admin/timetable/add-row")    # 룸1 + slot
    admin_client.post("/admin/timetable/add-room")   # 룸2
    with get_session() as db:
        sid = db.exec(select(Timeslot)).first().id
        rid2 = sorted(db.exec(select(Room)), key=lambda r: r.id)[-1].id
    admin_client.post(f"/admin/timetable/room/{rid2}/remove")
    admin_client.post(f"/admin/timetable/slot/{sid}/remove")
    with get_session() as db:
        assert len(list(db.exec(select(Room)))) == 1
        assert list(db.exec(select(Timeslot))) == []


def test_schedule_multiday_date_tabs(client, admin_client):
    # 공개 타임테이블도 여러 날이면 날짜 탭 + 날짜 캡션으로 나눠 보여준다
    admin_client.post("/admin/rooms", data={"name": "Room A", "sort_order": "0"})
    admin_client.post("/admin/timeslots", data={
        "date": "2026-09-12", "start_time": "10:00",
        "slot_minutes": "45", "break_minutes": "0", "count": "1"})
    admin_client.post("/admin/timeslots", data={
        "date": "2026-09-13", "start_time": "14:00",
        "slot_minutes": "45", "break_minutes": "0", "count": "1"})

    page = client.get("/schedule").text
    assert "date-tabs" in page                         # 날짜 탭 영역
    assert "09.12" in page and "09.13" in page          # 두 날짜 탭
    assert "2026년 9월 12일" in page and "2026년 9월 13일" in page  # 날짜 캡션
    assert "10:00–10:45" in page and "14:00–14:45" in page  # 두 날 표 모두 렌더


def test_nav_shows_participant_items_only(client):
    # 공개 네비: 주제 등록·목록·타임테이블만. '내 주제 수정' 탭·전광판은 빠짐
    nav = client.get("/topics").text
    for label in ["주제 등록", "주제 목록", "타임테이블"]:
        assert label in nav
    assert "내 주제 수정" not in nav
    assert "전광판 (Display Board)" not in nav


def _submit(client, *, email, title, pycon_id=0):
    login(client, email, pycon_id)
    r = client.post("/topics/new", data={"title": title, "description": "d"})
    assert r.status_code == 200


def test_home_requires_login(client):
    # 신원 없으면 홈은 '로그인 필요'로 막힌다 (soft login)
    r = client.get("/")
    assert "로그인이 필요" in r.text


def test_my_page_lists_my_topics_and_opens(client):
    # 같은 신원으로 여러 주제 → MY(/my) 대시보드 리스트, 항목 링크로 수정 진입
    login(client, email="me@x.com")
    client.post("/topics/new", data={"title": "주제 하나", "description": "d"})
    client.post("/topics/new", data={"title": "주제 둘", "description": "d"})
    my = client.get("/my").text
    assert "주제 하나" in my and "주제 둘" in my   # 둘 다 내 주제로 노출
    with get_session() as db:
        tid = db.exec(select(Topic).where(Topic.title == "주제 하나")).first().id
    assert f'href="/manage/{tid}"' in my          # 항목이 관리 페이지 링크
    r = client.get(f"/manage/{tid}")              # 클릭 = 관리 페이지
    assert "내 주제 관리" in r.text and "주제 하나" in r.text


def test_home_is_submission_form(client):
    # 로그인 첫 화면(/) = 주제 등록 폼 (함께 이야기할 주제를 제안하세요)
    login(client, email="me@x.com")
    home = client.get("/").text
    assert "주제를 제안하세요" in home          # hero 카피
    assert 'name="title"' in home and 'name="host_email"' not in home
    # /topics/new 는 홈으로 리다이렉트
    r = client.get("/topics/new", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_manage_rejects_non_owner(client):
    # 다른 신원의 주제는 관리/수정/삭제 불가 (소유권 보호 — pycon_id 기준)
    _submit(client, email="other@x.com", title="남의 주제")
    with get_session() as db:
        other_id = db.exec(select(Topic)).first().id
    login(client, email="me@x.com")               # 다른 사람으로 로그인
    assert "권한이 없" in client.get(f"/manage/{other_id}").text
    r = client.post(f"/manage/{other_id}/edit", data={"title": "탈취"})
    assert "권한이 없" in r.text
    with get_session() as db:                      # 제목 안 바뀜
        assert db.get(Topic, other_id).title == "남의 주제"


def test_manage_requires_login(client):
    # 미로그인 시 관리 페이지 접근 → 로그인 필요
    _submit(client, email="owner@x.com", title="주제")
    with get_session() as db:
        tid = db.exec(select(Topic)).first().id
    client.post("/logout")
    assert "로그인이 필요" in client.get(f"/manage/{tid}").text


def test_manage_redirects_to_my(client):
    # 옛 '내 주제 수정' 경로는 MY로 리다이렉트
    r = client.get("/manage", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/my"


def test_auth_check_probe(client):
    # 로그인 게이트의 새 창 로그인 완료 확인 프로브
    assert client.get("/auth/check").json() == {"authed": False}
    login(client, "me@x.com")
    assert client.get("/auth/check").json() == {"authed": True}


def test_login_gate_has_new_window_button(client):
    # 미로그인 화면에 새 창 로그인 버튼 + /auth/check 폴링 JS
    page = client.get("/topics/new").text   # 게이트로 리다이렉트
    assert "pycon-login-btn" in page and "/auth/check" in page


def test_register_requires_login(client):
    # /topics/new 는 신원(소프트 로그인) 필요 — 미로그인 시 막힘
    assert "로그인이 필요" in client.get("/topics/new").text
    # POST 도 막힘 + 미생성
    r = client.post("/topics/new", data={"title": "막힐 주제"})
    assert "로그인이 필요" in r.text
    with get_session() as db:
        assert db.exec(select(Topic)).first() is None


def test_topics_new_form_shows_after_login(client):
    # 로그인하면 등록 폼 노출(이메일 입력칸 없음 — 신원에서 공급), eyebrow 없음
    login(client, "me@x.com")
    page = client.get("/topics/new").text
    assert 'name="title"' in page and 'name="host_name"' in page
    assert 'name="host_email"' not in page          # 이메일은 폼에 없음
    assert "me@x.com" in page                        # 등록 계정 표시
    assert 'class="eyebrow"' not in page             # 작은 노란 글씨 제거


def test_dev_login_disabled_blocks_login(client, monkeypatch):
    # DEV_LOGIN_ENABLED 가 꺼지면 dev 로그인은 신원을 만들지 않는다
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "dev_login_enabled", False)
    client.post("/dev/login", data={"email": "me@x.com"})
    assert "로그인이 필요" in client.get("/").text


def test_board_qr_set_and_shown(admin_client, client):
    # 어드민에서 QR(이미지 URL + 설명) 등록 → 전광판 하단에 노출
    admin_client.post("/admin/board/qr/1", data={
        "image_url": "https://example.com/qr1.png", "caption": "행사 안내"})
    with get_session() as db:
        qr = db.exec(select(BoardQR).where(BoardQR.slot == 1)).first()
    assert qr and qr.image_url == "https://example.com/qr1.png"
    assert qr.caption == "행사 안내"
    board = client.get("/board").text
    assert "board-qr" in board
    assert "https://example.com/qr1.png" in board and "행사 안내" in board


def test_board_qr_hidden_without_image(admin_client, client):
    # 설명만 있고 이미지가 없으면 전광판에 표시되지 않음
    admin_client.post("/admin/board/qr/1", data={"caption": "이미지 없음"})
    board = client.get("/board").text
    assert "board-qr" not in board and "이미지 없음" not in board


def test_board_qr_remove_image(admin_client, client):
    admin_client.post("/admin/board/qr/2", data={
        "image_url": "https://example.com/qr2.png", "caption": "설문"})
    assert "https://example.com/qr2.png" in client.get("/board").text
    # 이미지 제거 → 전광판에서 사라짐
    admin_client.post("/admin/board/qr/2",
                      data={"remove_image": "1", "caption": "설문"})
    with get_session() as db:
        assert db.exec(select(BoardQR).where(BoardQR.slot == 2)).first().image_url is None
    assert "https://example.com/qr2.png" not in client.get("/board").text


def test_board_qr_invalid_slot_ignored(admin_client):
    r = admin_client.post("/admin/board/qr/9",
                          data={"image_url": "https://example.com/x.png"},
                          follow_redirects=False)
    assert r.status_code == 303
    with get_session() as db:
        assert db.exec(select(BoardQR)).first() is None


def test_board_renders(client):
    resp = client.get("/board")
    assert resp.status_code == 200
    assert "전광판" in resp.text


def test_board_shows_full_timetable(client, admin_client):
    # 전광판은 시간과 무관하게 전체 타임테이블의 모든 배정 세션을 카드로 표시
    room_id, ts_id = _seed_room_and_slot(admin_client)
    token = _submit_topic(client, title="전광판 카드 세션")
    client.post(f"/schedule/{token}/take", data={"slot": f"{room_id}:{ts_id}"})

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
        rooms = list(db.exec(select(Room)))
        slots = list(db.exec(select(Timeslot)))
        entries = list(db.exec(select(ScheduleEntry)))
        topics = list(db.exec(select(Topic)))
        assert len(rooms) == 5
        assert len(slots) == 8
        assert any(s.is_closed for s in slots)
        # 모든 열린 칸(열린 슬롯 × 룸)이 빠짐없이 채워진다
        open_slots = [s for s in slots if not s.is_closed]
        expected = len(open_slots) * len(rooms)
        assert len(entries) == expected
        assert len(topics) == expected
        filled = {(e.room_id, e.timeslot_id) for e in entries}
        for s in open_slots:
            for r in rooms:
                assert (r.id, s.id) in filled  # 빈 칸 없음

    # 공개 화면에 데모 데이터가 보임 (demo data visible publicly)
    assert "파이썬 타입 힌트" in client.get("/topics").text
    assert "키노트" in client.get("/schedule").text

    # 전광판: 전 세션이 가득 차서 빈 슬롯(비어있음)이 없어야 함
    board = client.get("/board").text
    assert "파이썬 타입 힌트" in board       # 배정된 세션
    assert "비어있음 (open)" not in board     # 빈 칸 없음 (모두 채워짐)

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
    # 비로그인 시드 시도 → 홈으로 리다이렉트(차단), 데이터 변화 없음
    from app.models import Room
    r = client.post("/admin/seed", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    with get_session() as db:
        assert list(db.exec(select(Room))) == []


def test_admin_requires_auth(client):
    # 비로그인/비관리자 → 관리 페이지 접근 차단(홈으로 리다이렉트)
    r = client.get("/admin/topics", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_non_admin_identity_blocked(client):
    # 로그인은 했지만 ADMIN_EMAILS 에 없는 이메일 → 관리자 차단
    login(client, "someone@x.com")
    r = client.get("/admin/topics", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    # /admin 은 '관리자 아님' 안내
    assert "관리자가 아닙니다" in client.get("/admin").text


def test_admin_email_grants_access_and_tab(client):
    # ADMIN_EMAILS 의 이메일로 로그인하면 관리자 접근 + nav 에 관리자 탭
    login(client, "admin@test.com")
    assert "주제 모더레이션" in client.get("/admin/topics").text   # 관리 페이지 접근
    assert "관리자" in client.get("/").text                        # 홈 nav 에 관리자 탭


def test_language_toggle_switches_to_english(client):
    login(client, "me@x.com")
    # 기본은 한국어 — 헤더에 한국어 네비, html lang=ko
    ko = client.get("/topics/new")
    assert 'lang="ko"' in ko.text
    assert "주제 등록" in ko.text

    # /lang/en 으로 쿠키 세팅 후 같은 페이지로 리다이렉트
    r = client.get("/lang/en?next=/topics/new", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/topics/new"
    assert "lang=en" in r.headers.get("set-cookie", "")

    # 쿠키가 적용되면 영어로 렌더 (html lang=en, 영어 라벨, 한국어 네비 사라짐)
    en = client.get("/topics/new")
    assert 'lang="en"' in en.text
    assert "Submit Topic" in en.text
    assert "주제 등록" not in en.text

    # 다시 한국어로 (toggle back)
    client.get("/lang/ko?next=/", follow_redirects=False)
    assert "주제 등록" in client.get("/topics/new").text


def test_language_toggle_blocks_open_redirect(client):
    # next 가 외부/프로토콜 상대 경로면 무시하고 홈으로 (오픈 리다이렉트 방지)
    for bad in ["//evil.com", "https://evil.com", "javascript:alert(1)"]:
        r = client.get(f"/lang/en?next={bad}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"


def test_admin_hide_topic_removes_from_public(client, admin_client):
    _submit_topic(client, title="숨길 주제 (Hide me)")
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
