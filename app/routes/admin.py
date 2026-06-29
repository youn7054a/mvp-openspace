"""관리자 페이지 (Admin): /admin, /admin/topics, /admin/rooms, /admin/timeslots."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta

from fasthtml.common import (
    A,
    Button,
    Div,
    Form,
    H1,
    H2,
    Img,
    Input,
    Label,
    Li,
    Option,
    P,
    RedirectResponse,
    Script,
    Section,
    Select,
    Small,
    Span,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Tr,
    Ul,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from starlette.datastructures import UploadFile

from ..components import field, layout, notice
from ..database import get_session
from ..i18n import t
from ..models import BoardQR, Room, ScheduleEntry, Timeslot, Topic, utcnow
from ..queries import (
    BOARD_QR_SLOTS,
    all_rooms,
    all_timeslots,
    board_qrs,
    entry_for_topic,
    schedule_map,
    topics_by_id,
)
from ..auth import identity_from_session, is_admin_email, note_identity
from ..uploads import (
    UploadError,
    delete_local_image,
    normalize_image_url,
    save_image,
)


def _admin_layout(title, *content):
    nav = Section(
        A(t("타임테이블", "Timetable"), href="/admin/timetable", cls="nav-link"), " · ",
        A(t("주제", "Topics"), href="/admin/topics", cls="nav-link"), " · ",
        A(t("룸", "Rooms"), href="/admin/rooms", cls="nav-link"), " · ",
        A(t("타임슬롯", "Timeslots"), href="/admin/timeslots", cls="nav-link"), " · ",
        A(t("전광판 QR", "Board QR"), href="/admin/board", cls="nav-link"), " · ",
        A(t("← 사이트로", "← Site"), href="/", cls="nav-link"),
        cls="admin-nav",
    )
    return layout(title, H1(t("관리자", "Admin")), nav, *content)


def _require_admin(session):
    """관리자(ADMIN_EMAILS 신원) 아니면 RedirectResponse 반환, 맞으면 None.

    세션에 캐시된 신원의 이메일이 ADMIN_EMAILS 에 있으면 관리자. 신원이 없거나
    관리자가 아니면 홈으로 보낸다. nav 의 관리자 탭 노출을 위해 신원 contextvar 도 세팅.
    """
    identity = identity_from_session(session)
    note_identity(identity)
    if not is_admin_email(identity):
        return RedirectResponse("/", status_code=303)
    return None


def _ts_error(message: str):
    """타임슬롯 생성 오류 안내 (Timeslot generation error)."""
    return _admin_layout(
        t("타임슬롯 관리", "Timeslot Management"),
        notice(message, kind="error"),
        A(t("돌아가기", "Back"), href="/admin/timeslots", cls="btn secondary"),
    )


def _tt_swap(*, target="#tt-builder"):
    """빌더 HTMX 스왑 공통 속성 (common swap attrs for builder buttons/forms)."""
    return dict(hx_target=target, hx_swap="outerHTML")


def _row_time_cell(ts):
    """행(시간) 머리 — 시작·종료 인라인 편집 + 행 삭제."""
    return Div(
        Form(
            Input(type="time", name="start_time", value=f"{ts.starts_at:%H:%M}",
                  aria_label=t("시작", "Start"), cls="tt-time"),
            Span("–", cls="tt-dash"),
            Input(type="time", name="end_time", value=f"{ts.ends_at:%H:%M}",
                  aria_label=t("종료", "End"), cls="tt-time"),
            hx_post=f"/admin/timetable/slot/{ts.id}/time",
            hx_trigger="change", cls="tt-time-form", **_tt_swap(),
        ),
        Button("✕", type="button", title=t("이 시간(행) 삭제", "Delete row"),
               hx_post=f"/admin/timetable/slot/{ts.id}/remove",
               hx_confirm=t("이 시간 행을 삭제할까요?", "Delete this time row?"),
               cls="tt-del", **_tt_swap()),
        cls="tt-rowhead",
    )


def _room_head_cell(room):
    """열(방) 머리 — 이름 인라인 편집 + 열 삭제."""
    return Div(
        Form(
            Input(name="name", value=room.name, aria_label=t("방 이름", "Room name"),
                  cls="tt-room-name"),
            hx_post=f"/admin/timetable/room/{room.id}/rename",
            hx_trigger="change", cls="tt-room-form", **_tt_swap(),
        ),
        Button("✕", type="button", title=t("이 방(열) 삭제", "Delete column"),
               hx_post=f"/admin/timetable/room/{room.id}/remove",
               hx_confirm=t("이 방(열)을 삭제할까요?", "Delete this room column?"),
               cls="tt-del", **_tt_swap()),
        cls="tt-colhead",
    )


def _builder_partial(db):
    """워드 표 방식 편집기 (Word-processor-style editable timetable).

    행(시간) ＋는 아래로, 열(방) ＋는 옆으로 — 모든 열이 같은 시간 행을 공유한다.
    HTMX 로 이 Div(#tt-builder) 전체를 통째로 다시 그린다.
    """
    rooms = all_rooms(db)
    timeslots = all_timeslots(db)
    slots = schedule_map(db)
    topics = topics_by_id(db)

    add_col = Button("＋", type="button", title=t("방(열) 추가", "Add room column"),
                     hx_post="/admin/timetable/add-room",
                     cls="tt-add tt-add-col", **_tt_swap())
    header = Tr(
        Th(t("시간", "Time"), cls="tt-corner"),
        *[Th(_room_head_cell(r), cls="tt-col") for r in rooms],
        Th(add_col, cls="tt-addcol-cell"),
    )

    body_rows = []
    span = len(rooms) + 1  # 방 열들 + ＋열 (closed row spans these)
    for ts in timeslots:
        if ts.is_closed:
            body_rows.append(Tr(
                Th(_row_time_cell(ts), scope="row", cls="tt-row"),
                Td(f"🔒 {ts.closed_label}", colspan=span, cls="slot-closed"),
            ))
            continue
        cells = [Th(_row_time_cell(ts), scope="row", cls="tt-row")]
        for r in rooms:
            entry = slots.get((r.id, ts.id))
            topic = topics.get(entry.topic_id) if entry else None
            if topic and topic.is_active:
                cells.append(Td(topic.title, cls="slot-filled"))
            else:
                cells.append(Td(t("비어있음", "open"), cls="slot-open"))
        cells.append(Td("", cls="tt-addcol-cell"))  # ＋열 아래 빈 칸
        body_rows.append(Tr(*cells))

    add_row = Button(t("＋ 시간(행) 추가", "＋ Add row"), type="button",
                     hx_post="/admin/timetable/add-row",
                     cls="tt-add tt-add-row", **_tt_swap())

    children = [
        Div(Table(Thead(header), Tbody(*body_rows), cls="tt-edit schedule"),
            cls="schedule-scroll"),
        Div(add_row, cls="tt-addrow"),
    ]
    if not timeslots and not rooms:
        children.append(P(t("＋ 로 시간(행)과 방(열)을 추가해 표를 만드세요.",
                            "Build the table by adding rows and columns with ＋."),
                          cls="field-help"))
    return Div(*children, id="tt-builder", cls="tt-builder")


def _admin_sched_cell(topic, entry, rooms, open_ts, taken, room_by_id, ts_by_id):
    """주제별 타임테이블 배정 컨트롤 (Admin assign topic to a slot)."""
    if topic.deleted_at is not None:
        return "—"
    if entry:
        room = room_by_id.get(entry.room_id)
        ts = ts_by_id.get(entry.timeslot_id)
        label = f"{room.name if room else '?'} · {ts.time_label if ts else '?'}"
        return Div(
            Span(label, cls="sched-current"),
            Form(Button(t("배정 해제", "Unassign"), type="submit", cls="secondary"),
                 method="post", action=f"/admin/topics/{topic.id}/unschedule",
                 style="display:inline"),
            cls="sched-cell",
        )
    opts = [Option(f"{r.name} · {ts.time_label}", value=f"{r.id}:{ts.id}")
            for ts in open_ts for r in rooms if (r.id, ts.id) not in taken]
    if not opts:
        return Span(t("빈 슬롯 없음", "no open slot"), cls="sched-current")
    return Form(
        Select(Option(t("슬롯 선택", "choose"), value="", disabled=True, selected=True),
               *opts, name="slot", aria_label=t("슬롯", "slot")),
        Button(t("배정", "Assign"), type="submit"),
        method="post", action=f"/admin/topics/{topic.id}/schedule", cls="sched-cell",
    )


def _qr_form(slot: int, qr):
    """전광판 QR 한 슬롯 등록 폼 (image upload/URL + caption)."""
    img = qr.image_url if qr else None
    caption = qr.caption if qr else ""
    inner = []
    if img:
        inner.append(Div(
            Img(src=img, alt=f"QR {slot} {t('이미지', 'image')}", cls="edit-thumb"),
            Label(Input(type="checkbox", name="remove_image", value="1"),
                  " " + t("이미지 제거", "Remove image"), cls="checkbox-label"),
            cls="current-image",
        ))
    else:
        inner.append(Small(t("아직 등록된 QR 이미지가 없습니다.", "No QR image yet."),
                           cls="field-help"))
    inner += [
        Div(Label(t("QR 이미지 업로드", "Upload"), fr=f"qr{slot}-file"),
            Input(id=f"qr{slot}-file", name="image_file", type="file",
                  accept="image/png,image/jpeg,image/gif,image/webp"), cls="field"),
        Div(Label(t("또는 이미지 URL", "or Image URL"), fr=f"qr{slot}-url"),
            Input(id=f"qr{slot}-url", name="image_url", type="url", required=False,
                  placeholder="https://example.com/qr.png"), cls="field"),
        Div(Label(t("설명", "Caption"), fr=f"qr{slot}-caption"),
            Input(id=f"qr{slot}-caption", name="caption", value=caption,
                  placeholder=t("예: 행사 안내 / 설문 링크", "e.g. event info / survey link"),
                  required=False), cls="field"),
        Button(t("저장", "Save"), type="submit"),
    ]
    return Section(
        H2(f"QR {slot}"),
        Form(*inner, method="post", action=f"/admin/board/qr/{slot}",
             enctype="multipart/form-data", cls="qr-form"),
        cls="qr-block",
    )


def _demo_section():
    """데모 데이터 채우기/비우기 (Seed / clear demo data) — 테스트 편의용."""
    return Section(
        H2(t("데모 데이터", "Demo data")),
        Small(t("버튼 한 번으로 룸·타임슬롯(키노트 포함)·주제·타임테이블 배정을 채웁니다. "
                "기존 데이터는 모두 교체됩니다.",
                "One click fills rooms, slots, topics and the schedule — replaces existing data."),
              cls="field-help"),
        Div(
            Form(Button(t("데모 데이터 채우기", "Seed demo"), type="submit"),
                 method="post", action="/admin/seed",
                 onsubmit=f"return confirm('{t('기존 데이터를 모두 지우고 데모 데이터로 채웁니다. 계속할까요?', 'This will wipe existing data and load demo data. Continue?')}')",
                 style="display:inline"),
            " ",
            Form(Button(t("전체 비우기", "Clear all"), type="submit", cls="danger"),
                 method="post", action="/admin/wipe",
                 onsubmit=f"return confirm('{t('모든 주제·룸·타임슬롯·배정을 삭제합니다. 계속할까요?', 'This will delete all topics, rooms, timeslots and assignments. Continue?')}')",
                 style="display:inline"),
            cls="ts-controls",
        ),
    )


def _timeslot_item(ts):
    """타임슬롯 목록 항목 — 커스텀 라벨로 닫기 / 라벨 변경 / 열기 / 삭제."""
    when = f"{ts.starts_at:%Y-%m-%d %H:%M} → {ts.ends_at:%H:%M}"
    delete = Form(Button(t("삭제", "Delete"), type="submit", cls="danger"),
                  method="post", action=f"/admin/timeslots/{ts.id}/delete",
                  style="display:inline")
    if ts.is_closed:
        relabel = Form(
            Input(name="label", value=ts.label,
                  placeholder=t("라벨 (예: 키노트, 휴식)", "Label (e.g. Keynote, Break)"),
                  cls="ts-label-input"),
            Button(t("라벨 변경", "Relabel"), type="submit", cls="secondary"),
            method="post", action=f"/admin/timeslots/{ts.id}/close",
            style="display:inline-flex; gap:.4rem",
        )
        reopen = Form(Button(t("열기", "Open"), type="submit", cls="secondary"),
                      method="post", action=f"/admin/timeslots/{ts.id}/open",
                      style="display:inline")
        return Li(
            Span(when, cls="ts-when"),
            Span(f"🔒 {ts.closed_label}", cls="ts-tag"),
            Div(relabel, reopen, delete, cls="ts-controls"),
            cls="ts-closed",
        )
    close = Form(
        Input(name="label",
              placeholder=t("라벨로 닫기 (예: 키노트, 휴식)", "Close with label (e.g. Keynote, Break)"),
              cls="ts-label-input"),
        Button(t("닫기", "Close"), type="submit", cls="secondary"),
        method="post", action=f"/admin/timeslots/{ts.id}/close",
        style="display:inline-flex; gap:.4rem",
    )
    return Li(
        Span(when, cls="ts-when"),
        Div(close, delete, cls="ts-controls"),
    )


# 입력값으로 생성될 슬롯을 실시간 미리보기 (Live preview of generated slots)
_SLOT_PREVIEW_JS = """
(function () {
  function pad(n){ return (n < 10 ? '0' : '') + n; }
  function fmt(mins){ var h = Math.floor(mins/60) %% 24, m = mins %% 60; return pad(h)+':'+pad(m); }
  function gv(id){ var e = document.getElementById(id); return e ? e.value : ''; }
  function toMin(s){ var p = (s||'').split(':'); return (parseInt(p[0],10)||0)*60 + (parseInt(p[1],10)||0); }
  function calc() {
    var out = document.getElementById('slot-preview');
    if (!out) return;
    var cur = toMin(gv('f-start_time') || '10:00');
    var len = parseInt(gv('f-slot_minutes'),10) || 0;
    var brk = parseInt(gv('f-break_minutes'),10) || 0;
    var cnt = Math.min(parseInt(gv('f-count'),10) || 0, 50);
    if (len <= 0 || cnt <= 0) { out.textContent = '%s'; return; }
    var lines = [];
    for (var i = 0; i < cnt; i++) { lines.push((i+1) + '. ' + fmt(cur) + '–' + fmt(cur+len)); cur += len + brk; }
    out.innerHTML = '<strong>%s' + cnt + '%s</strong><br>' + lines.join('  ·  ');
  }
  document.addEventListener('input', calc);
  calc();
})();
"""


def register(app) -> None:
    @app.get("/admin")
    def admin_home(session):
        identity = identity_from_session(session)
        note_identity(identity)
        if is_admin_email(identity):
            return RedirectResponse("/admin/topics", status_code=303)
        # 관리자 권한 없음 — 로그인 안내 또는 권한 없음
        if identity:
            msg = t("이 계정은 관리자가 아닙니다.", "This account is not an admin.")
        else:
            msg = t("관리자 권한이 필요합니다. 먼저 로그인하세요.",
                    "Admin access required — please log in first.")
        return layout(
            t("관리자", "Admin"),
            H1(t("관리자", "Admin")),
            notice(msg, kind="error"),
            A(t("홈으로", "Home"), href="/", cls="btn secondary"),
        )

    # ---- 주제 모더레이션 (Topic moderation) ----
    @app.get("/admin/topics")
    def admin_topics(session):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            topics = list(db.exec(select(Topic).order_by(Topic.created_at.desc())))
            rooms = all_rooms(db)
            open_ts = [t for t in all_timeslots(db) if not t.is_closed]
            taken = schedule_map(db)
            entry_by_topic = {e.topic_id: e for e in taken.values()}
            room_by_id = {r.id: r for r in rooms}
            ts_by_id = {t.id: t for t in all_timeslots(db)}
            rows = []
            for tp in topics:
                state = []
                if tp.deleted_at is not None:
                    state.append(t("삭제됨", "deleted"))
                if tp.is_hidden:
                    state.append(t("숨김", "hidden"))
                state_label = ", ".join(state) or t("공개", "visible")
                actions = []
                if tp.deleted_at is None:
                    hide_label = (t("숨김 해제", "Unhide") if tp.is_hidden
                                  else t("숨기기", "Hide"))
                    actions.append(Form(
                        Button(hide_label, type="submit", cls="secondary"),
                        method="post", action=f"/admin/topics/{tp.id}/toggle-hide",
                        style="display:inline"))
                    actions.append(Form(
                        Button(t("삭제", "Delete"), type="submit", cls="danger"),
                        method="post", action=f"/admin/topics/{tp.id}/delete",
                        style="display:inline"))
                rows.append(Tr(
                    Td(tp.title),
                    Td(tp.display_host),
                    Td(state_label),
                    Td(_admin_sched_cell(tp, entry_by_topic.get(tp.id), rooms,
                                         open_ts, taken, room_by_id, ts_by_id)),
                    Td(*actions),
                ))
        table = Table(
            Thead(Tr(Th(t("제목", "Title")), Th(t("제안자", "Host")),
                     Th(t("상태", "Status")), Th(t("타임테이블", "Schedule")),
                     Th(t("작업", "Actions")))),
            *rows, cls="schedule",
        ) if rows else notice(t("주제가 없습니다.", "No topics."))
        return _admin_layout(t("주제 모더레이션", "Topic Moderation"),
                             _demo_section(),
                             H2(t("주제", "Topics")), table)

    # ---- 데모 데이터 (Demo data seeding) ----
    @app.post("/admin/seed")
    def admin_seed(session):
        if (redir := _require_admin(session)):
            return redir
        from ..seed import seed_demo
        with get_session() as db:
            stats = seed_demo(db)
        return _admin_layout(
            t("데모 데이터", "Demo data"),
            notice(f"{t('데모 데이터를 채웠습니다', 'Demo data seeded')} — "
                   f"{t('룸', 'rooms')} {stats['rooms']}, "
                   f"{t('타임슬롯', 'timeslots')} {stats['timeslots']}, "
                   f"{t('주제', 'topics')} {stats['topics']} "
                   f"({t('배정', 'scheduled')} {stats['scheduled']}).",
                   kind="success"),
            A(t("주제 보기", "Topics"), href="/admin/topics", cls="btn secondary"), " ",
            A(t("타임테이블 보기", "Timetable"), href="/schedule", cls="btn secondary"), " ",
            A(t("전광판 보기", "Board"), href="/board", cls="btn secondary"),
        )

    @app.post("/admin/wipe")
    def admin_wipe(session):
        if (redir := _require_admin(session)):
            return redir
        from ..seed import wipe_all
        with get_session() as db:
            wipe_all(db)
        return RedirectResponse("/admin/topics", status_code=303)

    # ---- 관리자 타임테이블 배정 (Admin scheduling) ----
    @app.post("/admin/topics/{topic_id}/schedule")
    def admin_topic_schedule(session, topic_id: int, slot: str = ""):
        if (redir := _require_admin(session)):
            return redir
        try:
            room_id, ts_id = (int(x) for x in slot.split(":"))
        except (ValueError, AttributeError):
            return RedirectResponse("/admin/topics", status_code=303)
        with get_session() as db:
            topic = db.get(Topic, topic_id)
            ts = db.get(Timeslot, ts_id)
            if not topic or topic.deleted_at is not None or not ts or ts.is_closed:
                return RedirectResponse("/admin/topics", status_code=303)
            entry = entry_for_topic(db, topic_id)
            try:
                if entry:
                    entry.room_id = room_id
                    entry.timeslot_id = ts_id
                    entry.updated_at = utcnow()
                    db.add(entry)
                else:
                    db.add(ScheduleEntry(topic_id=topic_id, room_id=room_id,
                                         timeslot_id=ts_id))
                db.commit()
            except IntegrityError:
                db.rollback()
                return _admin_layout(
                    t("주제 모더레이션", "Topic Moderation"),
                    notice(t("이미 사용 중인 슬롯입니다. 다른 슬롯을 고르세요.",
                             "That slot is already taken."), kind="error"),
                    A(t("돌아가기", "Back"), href="/admin/topics", cls="btn secondary"))
        return RedirectResponse("/admin/topics", status_code=303)

    @app.post("/admin/topics/{topic_id}/unschedule")
    def admin_topic_unschedule(session, topic_id: int):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            entry = entry_for_topic(db, topic_id)
            if entry:
                db.delete(entry)
                db.commit()
        return RedirectResponse("/admin/topics", status_code=303)

    @app.post("/admin/topics/{topic_id}/toggle-hide")
    def admin_topic_toggle(session, topic_id: int):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            topic = db.get(Topic, topic_id)
            if topic and topic.deleted_at is None:
                topic.is_hidden = not topic.is_hidden
                topic.updated_at = utcnow()
                db.add(topic)
                db.commit()
        return RedirectResponse("/admin/topics", status_code=303)

    @app.post("/admin/topics/{topic_id}/delete")
    def admin_topic_delete(session, topic_id: int):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            topic = db.get(Topic, topic_id)
            if topic:
                entry = db.exec(select(ScheduleEntry).where(
                    ScheduleEntry.topic_id == topic_id)).first()
                if entry:
                    db.delete(entry)
                topic.deleted_at = utcnow()
                topic.updated_at = utcnow()
                db.add(topic)
                db.commit()
        return RedirectResponse("/admin/topics", status_code=303)

    # ---- 타임테이블 짜기 (Word-table builder: rows=time, cols=rooms) ----
    @app.get("/admin/timetable")
    def admin_timetable(session):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            builder = _builder_partial(db)
        return _admin_layout(
            t("타임테이블 짜기", "Timetable Builder"),
            H2(t("타임테이블", "Timetable")),
            P(t("워드 표처럼 ＋로 시간(행)은 아래로, 방(열)은 옆으로 추가하세요. "
                "시간·방 이름은 칸을 눌러 바로 수정하고, ✕로 삭제합니다.",
                "Add rows/columns with ＋, edit inline, delete with ✕."),
              cls="field-help"),
            builder,
        )

    @app.post("/admin/timetable/add-row")
    def tt_add_row(session):
        """시간(행) 추가 — 직전 슬롯에 이어 같은 길이로 한 행 추가."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            # 룸을 따로 신경 안 써도 되게, 첫 행 추가 시 기본 방 1개 자동 생성
            if not all_rooms(db):
                db.add(Room(name="룸 1", sort_order=0))
                db.commit()
            existing = all_timeslots(db)
            if existing:
                last = existing[-1]  # 시간순 정렬이라 마지막이 가장 늦은 슬롯
                duration = last.ends_at - last.starts_at
                starts = last.ends_at
                ends = starts + (duration or timedelta(minutes=45))
            else:
                base = datetime.combine(date.today(), dtime(10, 0))
                starts, ends = base, base + timedelta(minutes=45)
            order = max((t.sort_order for t in existing), default=-1) + 1
            db.add(Timeslot(starts_at=starts, ends_at=ends, sort_order=order))
            db.commit()
            return _builder_partial(db)

    @app.post("/admin/timetable/add-room")
    def tt_add_room(session):
        """방(열) 추가 — 기본 이름 '룸 N'."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            rooms = all_rooms(db)
            order = max((r.sort_order for r in rooms), default=-1) + 1
            db.add(Room(name=f"룸 {len(rooms) + 1}", sort_order=order))
            db.commit()
            return _builder_partial(db)

    @app.post("/admin/timetable/slot/{slot_id}/time")
    def tt_slot_time(session, slot_id: int, start_time: str = "", end_time: str = ""):
        """행(시간) 인라인 수정 — 날짜는 유지, 시각만 갱신."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            ts = db.get(Timeslot, slot_id)
            if ts:
                try:
                    d = ts.starts_at.date()
                    s = datetime.combine(d, dtime.fromisoformat(start_time))
                    e = datetime.combine(d, dtime.fromisoformat(end_time))
                    if e > s:
                        ts.starts_at, ts.ends_at = s, e
                        ts.updated_at = utcnow()
                        db.add(ts)
                        db.commit()
                except (ValueError, TypeError):
                    pass  # 잘못된 입력은 무시하고 기존 값 유지
            return _builder_partial(db)

    @app.post("/admin/timetable/room/{room_id}/rename")
    def tt_room_rename(session, room_id: int, name: str = ""):
        """열(방) 이름 인라인 수정."""
        if (redir := _require_admin(session)):
            return redir
        name = (name or "").strip()
        with get_session() as db:
            room = db.get(Room, room_id)
            if room and name:
                room.name = name
                room.updated_at = utcnow()
                db.add(room)
                db.commit()
            return _builder_partial(db)

    @app.post("/admin/timetable/slot/{slot_id}/remove")
    def tt_slot_remove(session, slot_id: int):
        """행(시간) 삭제 — 해당 슬롯의 배정도 함께 제거."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            for e in db.exec(select(ScheduleEntry).where(
                    ScheduleEntry.timeslot_id == slot_id)):
                db.delete(e)
            ts = db.get(Timeslot, slot_id)
            if ts:
                db.delete(ts)
            db.commit()
            return _builder_partial(db)

    @app.post("/admin/timetable/room/{room_id}/remove")
    def tt_room_remove(session, room_id: int):
        """열(방) 삭제 — 해당 방의 배정도 함께 제거."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            for e in db.exec(select(ScheduleEntry).where(
                    ScheduleEntry.room_id == room_id)):
                db.delete(e)
            room = db.get(Room, room_id)
            if room:
                db.delete(room)
            db.commit()
            return _builder_partial(db)

    # ---- 전광판 QR (Display-board QR codes) ----
    @app.get("/admin/board")
    def admin_board(session):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            qrs = board_qrs(db)
        return _admin_layout(
            t("전광판 QR", "Board QR"),
            H2(t("전광판 QR 코드", "Display-board QR")),
            P(t("전광판 하단에 노출할 QR 코드 2개를 등록합니다. 각 QR에 이미지와 설명을 "
                "넣을 수 있어요. 이미지가 없는 QR은 전광판에 표시되지 않습니다.",
                "Register up to two QR codes shown at the bottom of the board."),
              cls="field-help"),
            Div(*[_qr_form(s, qrs.get(s)) for s in BOARD_QR_SLOTS], cls="qr-grid"),
        )

    @app.post("/admin/board/qr/{slot}")
    async def admin_board_qr_save(session, slot: int, caption: str = "",
                                  image_url: str = "", remove_image: str = "",
                                  image_file: UploadFile = None):
        if (redir := _require_admin(session)):
            return redir
        if slot not in BOARD_QR_SLOTS:
            return RedirectResponse("/admin/board", status_code=303)
        # 이미지: 업로드 우선, 없으면 URL (uploaded file wins, else pasted URL)
        try:
            stored = await save_image(image_file)
            new_url = stored or normalize_image_url(image_url)
        except UploadError as exc:
            return _admin_layout(
                t("전광판 QR", "Board QR"), notice(str(exc), kind="error"),
                A(t("돌아가기", "Back"), href="/admin/board", cls="btn secondary"))
        with get_session() as db:
            qr = db.exec(select(BoardQR).where(BoardQR.slot == slot)).first()
            if not qr:
                qr = BoardQR(slot=slot)
            old_url = qr.image_url
            if new_url:                      # 새 이미지로 교체
                qr.image_url = new_url
                if old_url and old_url != new_url:
                    delete_local_image(old_url)
            elif remove_image:               # 이미지 제거
                qr.image_url = None
                delete_local_image(old_url)
            qr.caption = (caption or "").strip()
            qr.updated_at = utcnow()
            db.add(qr)
            db.commit()
        return RedirectResponse("/admin/board", status_code=303)

    # ---- 룸 관리 (Room management) ----
    @app.get("/admin/rooms")
    def admin_rooms(session):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            rooms = all_rooms(db)
        items = [Li(f"{r.name} ({t('정렬 order', 'sort order')}={r.sort_order}) ",
                    Form(Button(t("삭제", "Delete"), type="submit", cls="danger"),
                         method="post", action=f"/admin/rooms/{r.id}/delete",
                         style="display:inline"))
                 for r in rooms] or [Li(t("룸이 없습니다.", "No rooms."))]
        return _admin_layout(
            t("룸 관리", "Room Management"),
            H2(t("룸 추가", "Add Room")),
            Form(
                field(t("이름", "Name"), "name"),
                field(t("정렬 순서", "Sort order"), "sort_order",
                      value="0", input_type="number", required=False),
                Button(t("추가", "Add"), type="submit"),
                method="post", action="/admin/rooms",
            ),
            H2(t("룸 목록", "Rooms")), Ul(*items),
        )

    @app.post("/admin/rooms")
    def admin_room_create(session, name: str, sort_order: int = 0):
        if (redir := _require_admin(session)):
            return redir
        name = (name or "").strip()
        if name:
            with get_session() as db:
                db.add(Room(name=name, sort_order=sort_order or 0))
                db.commit()
        return RedirectResponse("/admin/rooms", status_code=303)

    @app.post("/admin/rooms/{room_id}/delete")
    def admin_room_delete(session, room_id: int):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            # 해당 룸의 스케줄 먼저 제거 (free schedule entries first)
            for e in db.exec(select(ScheduleEntry).where(
                    ScheduleEntry.room_id == room_id)):
                db.delete(e)
            room = db.get(Room, room_id)
            if room:
                db.delete(room)
            db.commit()
        return RedirectResponse("/admin/rooms", status_code=303)

    # ---- 타임슬롯 관리 (Timeslot management) ----
    @app.get("/admin/timeslots")
    def admin_timeslots(session):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            timeslots = all_timeslots(db)
        items = [_timeslot_item(ts) for ts in timeslots] or \
            [Li(t("타임슬롯이 없습니다.", "No timeslots."))]
        gen_form = Form(
            Small(t("날짜와 시작 시각, 슬롯 길이만 정하면 연속 슬롯을 한 번에 만듭니다. "
                    "개수를 1로 두면 한 개만 추가돼요.",
                    "Set a date, start time and length — slots are generated in a row."),
                  cls="field-help"),
            Div(
                Div(Label(t("날짜", "Date"), fr="f-date"),
                    Input(id="f-date", name="date", type="date", required=True),
                    cls="field"),
                Div(Label(t("시작 시각", "Start time"), fr="f-start_time"),
                    Input(id="f-start_time", name="start_time", type="time",
                          value="10:00", required=True), cls="field"),
                cls="form-row",
            ),
            Div(
                Div(Label(t("슬롯 길이 (분 / min)", "Slot length (min)"), fr="f-slot_minutes"),
                    Input(id="f-slot_minutes", name="slot_minutes", type="number",
                          value="45", min="5", step="5", required=True), cls="field"),
                Div(Label(t("쉬는 시간 (분 / min)", "Break (min)"), fr="f-break_minutes"),
                    Input(id="f-break_minutes", name="break_minutes", type="number",
                          value="10", min="0", step="5"), cls="field"),
                Div(Label(t("슬롯 개수", "Count"), fr="f-count"),
                    Input(id="f-count", name="count", type="number",
                          value="6", min="1", max="50", required=True), cls="field"),
                cls="form-row",
            ),
            Div(t("생성될 슬롯 미리보기", "preview"), id="slot-preview", cls="slot-preview"),
            Button(t("타임슬롯 생성", "Generate slots"), type="submit"),
            method="post", action="/admin/timeslots",
        )
        return _admin_layout(
            t("타임슬롯 관리", "Timeslot Management"),
            H2(t("타임슬롯 일괄 생성", "Generate Timeslots")),
            gen_form,
            Script(_SLOT_PREVIEW_JS % (
                t("슬롯 길이와 개수를 입력하세요.", "Enter slot length and count."),
                t("생성될 슬롯 (", "Slots to create ("),
                t("개):", "):"),
            )),
            H2(t("타임슬롯 목록", "Timeslots")), Ul(*items),
        )

    @app.post("/admin/timeslots")
    def admin_timeslot_create(session, date: str, start_time: str,
                              slot_minutes: int = 45, break_minutes: int = 0,
                              count: int = 1):
        if (redir := _require_admin(session)):
            return redir
        try:
            base = datetime.fromisoformat(f"{date}T{start_time}")
        except (ValueError, TypeError):
            return _ts_error(t("날짜·시각 형식이 올바르지 않습니다.", "Invalid date/time."))
        if slot_minutes <= 0:
            return _ts_error(t("슬롯 길이는 1분 이상이어야 합니다.", "Length must be positive."))
        count = max(1, min(count, 50))           # 안전 상한 (cap at 50)
        break_minutes = max(0, break_minutes)

        with get_session() as db:
            existing = all_timeslots(db)
            next_order = max((t.sort_order for t in existing), default=-1) + 1
            cursor = base
            for i in range(count):
                end = cursor + timedelta(minutes=slot_minutes)
                db.add(Timeslot(starts_at=cursor, ends_at=end,
                                sort_order=next_order + i))
                cursor = end + timedelta(minutes=break_minutes)
            db.commit()
        return RedirectResponse("/admin/timeslots", status_code=303)

    @app.post("/admin/timeslots/{timeslot_id}/close")
    def admin_timeslot_close(session, timeslot_id: int, label: str = ""):
        """슬롯을 커스텀 라벨로 닫기 (Close a slot with a custom label).

        이미 닫힌 슬롯에 다시 호출하면 라벨만 변경 (relabel).
        """
        if (redir := _require_admin(session)):
            return redir
        label = (label or "").strip()
        with get_session() as db:
            ts = db.get(Timeslot, timeslot_id)
            if ts:
                if not ts.is_closed:
                    # 닫으면 그 슬롯의 배정을 해제 (free any scheduled topics)
                    for e in db.exec(select(ScheduleEntry).where(
                            ScheduleEntry.timeslot_id == timeslot_id)):
                        db.delete(e)
                ts.is_closed = True
                ts.label = label or "닫힘 (Closed)"
                ts.updated_at = utcnow()
                db.add(ts)
                db.commit()
        return RedirectResponse("/admin/timeslots", status_code=303)

    @app.post("/admin/timeslots/{timeslot_id}/open")
    def admin_timeslot_open(session, timeslot_id: int):
        """닫힌 슬롯 다시 열기 (Reopen a slot)."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            ts = db.get(Timeslot, timeslot_id)
            if ts:
                ts.is_closed = False
                ts.label = ""
                ts.updated_at = utcnow()
                db.add(ts)
                db.commit()
        return RedirectResponse("/admin/timeslots", status_code=303)

    @app.post("/admin/timeslots/{timeslot_id}/delete")
    def admin_timeslot_delete(session, timeslot_id: int):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            for e in db.exec(select(ScheduleEntry).where(
                    ScheduleEntry.timeslot_id == timeslot_id)):
                db.delete(e)
            ts = db.get(Timeslot, timeslot_id)
            if ts:
                db.delete(ts)
            db.commit()
        return RedirectResponse("/admin/timeslots", status_code=303)
