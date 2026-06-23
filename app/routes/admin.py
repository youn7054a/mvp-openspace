"""관리자 페이지 (Admin): /admin, /admin/topics, /admin/rooms, /admin/timeslots."""
from __future__ import annotations

from datetime import datetime, timedelta

from fasthtml.common import (
    A,
    Button,
    Div,
    Form,
    H1,
    H2,
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
    Td,
    Th,
    Thead,
    Tr,
    Ul,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..components import field, layout, notice
from ..database import get_session
from ..models import Room, ScheduleEntry, Timeslot, Topic, utcnow
from ..queries import all_rooms, all_timeslots, entry_for_topic, schedule_map
from ..security import (
    ADMIN_SESSION_KEY,
    is_admin,
    verify_admin_password,
)


def _admin_layout(title, *content):
    nav = Section(
        A("주제 (Topics)", href="/admin/topics", cls="nav-link"), " · ",
        A("룸 (Rooms)", href="/admin/rooms", cls="nav-link"), " · ",
        A("타임슬롯 (Timeslots)", href="/admin/timeslots", cls="nav-link"), " · ",
        Form(Button("로그아웃 (Logout)", type="submit", cls="secondary"),
             method="post", action="/admin/logout", style="display:inline"),
        cls="admin-nav",
    )
    return layout(title, H1("관리자 (Admin)"), nav, *content)


def _require_admin(session):
    """관리자 아니면 RedirectResponse 반환, 맞으면 None."""
    if not is_admin(session):
        return RedirectResponse("/admin", status_code=303)
    return None


def _ts_error(message: str):
    """타임슬롯 생성 오류 안내 (Timeslot generation error)."""
    return _admin_layout(
        "타임슬롯 관리 (Timeslot Management)",
        notice(message, kind="error"),
        A("돌아가기 (Back)", href="/admin/timeslots", cls="btn secondary"),
    )


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
            Form(Button("배정 해제 (Unassign)", type="submit", cls="secondary"),
                 method="post", action=f"/admin/topics/{topic.id}/unschedule",
                 style="display:inline"),
            cls="sched-cell",
        )
    opts = [Option(f"{r.name} · {ts.time_label}", value=f"{r.id}:{ts.id}")
            for ts in open_ts for r in rooms if (r.id, ts.id) not in taken]
    if not opts:
        return Span("빈 슬롯 없음 (no open slot)", cls="sched-current")
    return Form(
        Select(Option("슬롯 선택 (choose)", value="", disabled=True, selected=True),
               *opts, name="slot", aria_label="슬롯 (slot)"),
        Button("배정 (Assign)", type="submit"),
        method="post", action=f"/admin/topics/{topic.id}/schedule", cls="sched-cell",
    )


def _demo_section():
    """데모 데이터 채우기/비우기 (Seed / clear demo data) — 테스트 편의용."""
    return Section(
        H2("데모 데이터 (Demo data)"),
        Small("버튼 한 번으로 룸·타임슬롯(키노트 포함)·주제·타임테이블 배정을 채웁니다. "
              "기존 데이터는 모두 교체됩니다. "
              "(One click fills rooms, slots, topics and the schedule — replaces existing data.)",
              cls="field-help"),
        Div(
            Form(Button("데모 데이터 채우기 (Seed demo)", type="submit"),
                 method="post", action="/admin/seed",
                 onsubmit="return confirm('기존 데이터를 모두 지우고 데모 데이터로 채웁니다. 계속할까요?')",
                 style="display:inline"),
            " ",
            Form(Button("전체 비우기 (Clear all)", type="submit", cls="danger"),
                 method="post", action="/admin/wipe",
                 onsubmit="return confirm('모든 주제·룸·타임슬롯·배정을 삭제합니다. 계속할까요?')",
                 style="display:inline"),
            cls="ts-controls",
        ),
    )


def _timeslot_item(t):
    """타임슬롯 목록 항목 — 커스텀 라벨로 닫기 / 라벨 변경 / 열기 / 삭제."""
    when = f"{t.starts_at:%Y-%m-%d %H:%M} → {t.ends_at:%H:%M}"
    delete = Form(Button("삭제 (Delete)", type="submit", cls="danger"),
                  method="post", action=f"/admin/timeslots/{t.id}/delete",
                  style="display:inline")
    if t.is_closed:
        relabel = Form(
            Input(name="label", value=t.label, placeholder="라벨 (예: 키노트, 휴식)",
                  cls="ts-label-input"),
            Button("라벨 변경 (Relabel)", type="submit", cls="secondary"),
            method="post", action=f"/admin/timeslots/{t.id}/close",
            style="display:inline-flex; gap:.4rem",
        )
        reopen = Form(Button("열기 (Open)", type="submit", cls="secondary"),
                      method="post", action=f"/admin/timeslots/{t.id}/open",
                      style="display:inline")
        return Li(
            Span(when, cls="ts-when"),
            Span(f"🔒 {t.closed_label}", cls="ts-tag"),
            Div(relabel, reopen, delete, cls="ts-controls"),
            cls="ts-closed",
        )
    close = Form(
        Input(name="label", placeholder="라벨로 닫기 (예: 키노트, 휴식)",
              cls="ts-label-input"),
        Button("닫기 (Close)", type="submit", cls="secondary"),
        method="post", action=f"/admin/timeslots/{t.id}/close",
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
  function fmt(mins){ var h = Math.floor(mins/60) % 24, m = mins % 60; return pad(h)+':'+pad(m); }
  function gv(id){ var e = document.getElementById(id); return e ? e.value : ''; }
  function toMin(s){ var p = (s||'').split(':'); return (parseInt(p[0],10)||0)*60 + (parseInt(p[1],10)||0); }
  function calc() {
    var out = document.getElementById('slot-preview');
    if (!out) return;
    var cur = toMin(gv('f-start_time') || '10:00');
    var len = parseInt(gv('f-slot_minutes'),10) || 0;
    var brk = parseInt(gv('f-break_minutes'),10) || 0;
    var cnt = Math.min(parseInt(gv('f-count'),10) || 0, 50);
    if (len <= 0 || cnt <= 0) { out.textContent = '슬롯 길이와 개수를 입력하세요.'; return; }
    var lines = [];
    for (var i = 0; i < cnt; i++) { lines.push((i+1) + '. ' + fmt(cur) + '–' + fmt(cur+len)); cur += len + brk; }
    out.innerHTML = '<strong>생성될 슬롯 (' + cnt + '개):</strong><br>' + lines.join('  ·  ');
  }
  document.addEventListener('input', calc);
  calc();
})();
"""


def register(app) -> None:
    @app.get("/admin")
    def admin_home(session):
        if is_admin(session):
            return RedirectResponse("/admin/topics", status_code=303)
        return layout(
            "관리자 로그인 (Admin Login)",
            H1("관리자 로그인 (Admin Login)"),
            Form(
                field("비밀번호 (Password)", "password", input_type="password"),
                Button("로그인 (Login)", type="submit"),
                method="post", action="/admin/login",
            ),
        )

    @app.post("/admin/login")
    def admin_login(session, password: str = ""):
        if verify_admin_password(password):
            session[ADMIN_SESSION_KEY] = True
            return RedirectResponse("/admin/topics", status_code=303)
        return layout(
            "관리자 로그인 (Admin Login)",
            notice("비밀번호가 올바르지 않습니다. (Incorrect password.)", kind="error"),
            A("다시 시도 (Try again)", href="/admin", cls="btn secondary"),
        )

    @app.post("/admin/logout")
    def admin_logout(session):
        session.pop(ADMIN_SESSION_KEY, None)
        return RedirectResponse("/admin", status_code=303)

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
            for t in topics:
                state = []
                if t.deleted_at is not None:
                    state.append("삭제됨 (deleted)")
                if t.is_hidden:
                    state.append("숨김 (hidden)")
                state_label = ", ".join(state) or "공개 (visible)"
                actions = []
                if t.deleted_at is None:
                    hide_label = ("숨김 해제 (Unhide)" if t.is_hidden
                                  else "숨기기 (Hide)")
                    actions.append(Form(
                        Button(hide_label, type="submit", cls="secondary"),
                        method="post", action=f"/admin/topics/{t.id}/toggle-hide",
                        style="display:inline"))
                    actions.append(Form(
                        Button("삭제 (Delete)", type="submit", cls="danger"),
                        method="post", action=f"/admin/topics/{t.id}/delete",
                        style="display:inline"))
                rows.append(Tr(
                    Td(t.title),
                    Td(t.display_host),
                    Td(state_label),
                    Td(_admin_sched_cell(t, entry_by_topic.get(t.id), rooms,
                                         open_ts, taken, room_by_id, ts_by_id)),
                    Td(*actions),
                ))
        table = Table(
            Thead(Tr(Th("제목 (Title)"), Th("제안자 (Host)"), Th("상태 (Status)"),
                     Th("타임테이블 (Schedule)"), Th("작업 (Actions)"))),
            *rows, cls="schedule",
        ) if rows else notice("주제가 없습니다. (No topics.)")
        return _admin_layout("주제 모더레이션 (Topic Moderation)",
                             _demo_section(),
                             H2("주제 (Topics)"), table)

    # ---- 데모 데이터 (Demo data seeding) ----
    @app.post("/admin/seed")
    def admin_seed(session):
        if (redir := _require_admin(session)):
            return redir
        from ..seed import seed_demo
        with get_session() as db:
            stats = seed_demo(db)
        return _admin_layout(
            "데모 데이터 (Demo data)",
            notice(f"데모 데이터를 채웠습니다 — 룸 {stats['rooms']}개, "
                   f"타임슬롯 {stats['timeslots']}개, 주제 {stats['topics']}개 "
                   f"(배정 {stats['scheduled']}개). "
                   "(Demo data seeded.)", kind="success"),
            A("주제 보기 (Topics)", href="/admin/topics", cls="btn secondary"), " ",
            A("타임테이블 보기 (Timetable)", href="/schedule", cls="btn secondary"), " ",
            A("전광판 보기 (Board)", href="/board", cls="btn secondary"),
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
                    "주제 모더레이션 (Topic Moderation)",
                    notice("이미 사용 중인 슬롯입니다. 다른 슬롯을 고르세요. "
                           "(That slot is already taken.)", kind="error"),
                    A("돌아가기 (Back)", href="/admin/topics", cls="btn secondary"))
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

    # ---- 룸 관리 (Room management) ----
    @app.get("/admin/rooms")
    def admin_rooms(session):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            rooms = all_rooms(db)
        items = [Li(f"{r.name} (정렬 order={r.sort_order}) ",
                    Form(Button("삭제 (Delete)", type="submit", cls="danger"),
                         method="post", action=f"/admin/rooms/{r.id}/delete",
                         style="display:inline"))
                 for r in rooms] or [Li("룸이 없습니다. (No rooms.)")]
        return _admin_layout(
            "룸 관리 (Room Management)",
            H2("룸 추가 (Add Room)"),
            Form(
                field("이름 (Name)", "name"),
                field("정렬 순서 (Sort order)", "sort_order",
                      value="0", input_type="number", required=False),
                Button("추가 (Add)", type="submit"),
                method="post", action="/admin/rooms",
            ),
            H2("룸 목록 (Rooms)"), Ul(*items),
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
        items = [_timeslot_item(t) for t in timeslots] or \
            [Li("타임슬롯이 없습니다. (No timeslots.)")]
        gen_form = Form(
            Small("날짜와 시작 시각, 슬롯 길이만 정하면 연속 슬롯을 한 번에 만듭니다. "
                  "개수를 1로 두면 한 개만 추가돼요. "
                  "(Set a date, start time and length — slots are generated in a row.)",
                  cls="field-help"),
            Div(
                Div(Label("날짜 (Date)", fr="f-date"),
                    Input(id="f-date", name="date", type="date", required=True),
                    cls="field"),
                Div(Label("시작 시각 (Start time)", fr="f-start_time"),
                    Input(id="f-start_time", name="start_time", type="time",
                          value="10:00", required=True), cls="field"),
                cls="form-row",
            ),
            Div(
                Div(Label("슬롯 길이 (분 / min)", fr="f-slot_minutes"),
                    Input(id="f-slot_minutes", name="slot_minutes", type="number",
                          value="45", min="5", step="5", required=True), cls="field"),
                Div(Label("쉬는 시간 (분 / min)", fr="f-break_minutes"),
                    Input(id="f-break_minutes", name="break_minutes", type="number",
                          value="10", min="0", step="5"), cls="field"),
                Div(Label("슬롯 개수 (Count)", fr="f-count"),
                    Input(id="f-count", name="count", type="number",
                          value="6", min="1", max="50", required=True), cls="field"),
                cls="form-row",
            ),
            Div("생성될 슬롯 미리보기 (preview)", id="slot-preview", cls="slot-preview"),
            Button("타임슬롯 생성 (Generate slots)", type="submit"),
            method="post", action="/admin/timeslots",
        )
        return _admin_layout(
            "타임슬롯 관리 (Timeslot Management)",
            H2("타임슬롯 일괄 생성 (Generate Timeslots)"),
            gen_form,
            Script(_SLOT_PREVIEW_JS),
            H2("타임슬롯 목록 (Timeslots)"), Ul(*items),
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
            return _ts_error("날짜·시각 형식이 올바르지 않습니다. (Invalid date/time.)")
        if slot_minutes <= 0:
            return _ts_error("슬롯 길이는 1분 이상이어야 합니다. (Length must be positive.)")
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
