"""매직링크 주제 관리 (Manage My Topic): /manage/{token}."""
from __future__ import annotations

from fasthtml.common import (
    A,
    Button,
    Div,
    Fieldset,
    Form,
    H1,
    H2,
    Img,
    Input,
    Label,
    Legend,
    P,
    RedirectResponse,
    Script,
    Section,
    Small,
    Span,
    Table,
    Td,
    Th,
    Thead,
    Tr,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from starlette.datastructures import UploadFile

from ..components import (
    PYCON_SESSION_URL,
    PYCON_SIGNIN_URL,
    date_tabs,
    field,
    layout,
    notice,
)
from ..database import get_session
from ..mailer import send_magic_link
from ..models import ScheduleEntry, Timeslot, Topic, utcnow
from ..queries import all_rooms, all_timeslots, entry_for_topic, schedule_map
from ..security import generate_token, hash_token, token_expiry
from ..uploads import (
    UploadError,
    delete_local_image,
    normalize_image_url,
    save_image,
)

PANEL_ID = "manage-panel"


# PyCon 로그인으로 '내 주제 수정'에 바로 진입 (Login → open my topic).
# 로그인 확인되면 세션 이메일을 폼에 채워 본인 주제 조회를 자동 제출한다.
# 미로그인이면 버튼으로 새 창에서 로그인을 유도하고, 완료를 주기적으로 확인해
# 자동으로 이어간다(팝업 차단 회피 위해 버튼 클릭 사용).
_MANAGE_LOGIN_JS = """
(function () {
  var EP = '%s';
  var SIGNIN = '%s';
  var form = document.getElementById('manage-resolve');
  var emailField = document.getElementById('manage-email');
  var gate = document.getElementById('manage-gate');
  if (!form || !emailField) return;
  var done = false, settled = false, poll = null;
  function proceed(email) {
    if (done) return; done = true;
    if (poll) { clearInterval(poll); poll = null; }
    emailField.value = email;
    form.submit();  // 본인 주제 조회 (POST /manage/open)
  }
  function fail(text) { if (gate) gate.textContent = text; }
  function check(cb) {
    fetch(EP, { credentials: 'include', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        var authed = b && b.meta && b.meta.is_authenticated;
        var email = b && b.data && b.data.user && b.data.user.email;
        cb(authed && email ? email : null, true);
      })
      .catch(function () { cb(null, false); });
  }
  function showLoginPrompt() {
    if (!gate) return;
    gate.className = 'notice notice-info'; gate.textContent = '';
    var msg = document.createElement('p');
    msg.textContent = 'PyCon 로그인이 필요합니다. 아래 버튼을 누르면 새 창에서 ' +
      '로그인할 수 있습니다. 로그인하면 자동으로 진행됩니다. ' +
      '(Log in via PyCon in the new window — this page continues automatically.)';
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'btn'; btn.textContent = 'PyCon 로그인 (새 창)';
    btn.addEventListener('click', function () {
      window.open(SIGNIN, 'pycon-login', 'width=520,height=720');
      if (!poll) poll = setInterval(function () {
        check(function (email) { if (email) proceed(email); });
      }, 3000);  // 로그인 완료를 주기적으로 확인
    });
    gate.appendChild(msg); gate.appendChild(btn);
  }
  setTimeout(function () {
    if (!settled) { settled = true;
      fail('PyCon 로그인 확인이 지연됩니다. 이메일로 받은 매직링크를 사용해 주세요.'); }
  }, 8000);
  check(function (email, ok) {
    if (settled) return; settled = true;
    if (email) proceed(email);              // 로그인됨 → 진행
    else if (ok) showLoginPrompt();          // 확정 미로그인 → 새 창 로그인 유도
    else fail('PyCon 로그인 확인에 실패했습니다. 이메일로 받은 매직링크를 사용해 주세요.');
  });
})();
""" % (PYCON_SESSION_URL, PYCON_SIGNIN_URL)


def _issue_token(session, topic: Topic) -> str:
    """본인 확인된 주제에 새 매직링크 토큰 발급 (mint a fresh edit token).

    직접 수정 페이지로 바로 보내는 동시에, 같은 링크를 이메일로도 발송한다 —
    다음엔 메일의 매직링크로 바로 들어올 수 있게.

    주의: 이메일은 클라이언트(PyCon 세션)에서 전달되어 서버가 직접 검증하지
    못한다 — 매직링크와 동일한 신뢰 수준의 편의 기능이다. (README 보안 참고)
    """
    raw, token_hash = generate_token()
    topic.edit_token_hash = token_hash
    topic.edit_token_expires_at = token_expiry()
    topic.updated_at = utcnow()
    session.add(topic)
    session.commit()
    send_magic_link(topic.host_email, raw, topic.title)
    return raw


def _topics_for_email(session, email: str) -> list[Topic]:
    """이메일로 본인 주제 조회 (삭제 제외, 대소문자 무시)."""
    email = email.lower()
    rows = session.exec(
        select(Topic).where(Topic.deleted_at == None)  # noqa: E711
        .order_by(Topic.created_at.desc())
    )
    return [t for t in rows if (t.host_email or "").strip().lower() == email]


def _load_topic(session, token: str) -> Topic | None:
    """토큰으로 유효한 주제 조회 (삭제/만료 제외)."""
    topic = session.exec(
        select(Topic).where(Topic.edit_token_hash == hash_token(token))
    ).first()
    if not topic or topic.deleted_at is not None:
        return None
    expires = topic.edit_token_expires_at
    if expires is not None and expires.replace(tzinfo=None) < utcnow().replace(tzinfo=None):
        return None
    return topic


def _slot_cell(topic: Topic, room, ts, entry, current_entry):
    """타임테이블 한 칸 (One room×timeslot cell).

    내 자리·사용 중·빈 칸을 색으로 구분하고, 빈 칸은 눌러서 바로 등록/이동.
    """
    is_mine = current_entry and entry and entry.id == current_entry.id
    if is_mine:
        return Td(Span("✓ 내 주제 (My topic)", cls="slot-tag"),
                  cls="slot-mine", aria_label="현재 내 자리 (My current slot)")
    if entry:  # 다른 주제가 사용 중 (taken by someone else)
        return Td(Span("사용 중 (Taken)", cls="slot-tag"), cls="slot-taken")
    # 빈 칸 — 누르면 이 자리로 등록/이동 (open: click to take/move here)
    label = "여기로 이동 (Move here)" if current_entry else "이 자리 잡기 (Take)"
    return Td(
        Button(label, type="button",
               hx_post=f"/manage/{_tok(topic)}/schedule",
               hx_vals=f'{{"slot": "{room.id}:{ts.id}"}}',
               hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
               cls="slot-pick"),
        cls="slot-open",
    )


def _schedule_grid(session, topic: Topic, current_entry, rooms, timeslots, taken):
    """클릭형 타임테이블 (Interactive timetable) — 빈 칸을 눌러 슬롯 선택."""
    header = Tr(Th("시간 / 룸 (Time / Room)"), *[Th(r.name) for r in rooms])
    rows = []
    for ts in timeslots:
        if ts.is_closed:  # 닫힌 슬롯(키노트·휴식 등)은 예약 불가
            rows.append(Tr(
                Th(ts.time_label, scope="row"),
                Td(ts.closed_label, colspan=len(rooms), cls="slot-closed"),
            ))
            continue
        cells = [Th(ts.time_label, scope="row")]
        for room in rooms:
            entry = taken.get((room.id, ts.id))
            cells.append(_slot_cell(topic, room, ts, entry, current_entry))
        rows.append(Tr(*cells))
    return Div(
        Table(Thead(header), *rows, cls="schedule manage-schedule"),
        cls="schedule-scroll",
    )


def _schedule_picker(session, topic: Topic, current_entry, rooms, timeslots):
    """타임테이블 선택 영역 — 여러 날이면 날짜 탭으로 나눠 보여준다.

    공용 date_tabs(순수 CSS 라디오 탭)로 렌더하므로 HTMX 패널 스왑 후에도
    동작이 유지된다. 각 날짜 표 위에는 날짜 제목이 붙는다.
    """
    taken = schedule_map(session)
    days = sorted({ts.starts_at.date().isoformat() for ts in timeslots})

    # 현재 내 자리가 있는 날을 기본 선택 (default to the day my topic sits on).
    default_day = None
    if current_entry:
        cur_ts = session.get(Timeslot, current_entry.timeslot_id)
        if cur_ts:
            default_day = cur_ts.starts_at.date().isoformat()

    def render_day(day: str):
        day_slots = [ts for ts in timeslots
                     if ts.starts_at.date().isoformat() == day]
        return _schedule_grid(session, topic, current_entry, rooms,
                              day_slots, taken)

    return date_tabs(days, render_day, id_prefix="mday", default_day=default_day)


def _schedule_section(session, topic: Topic):
    """타임테이블 등록/변경/취소 UI — 표에서 빈 칸을 눌러 선택."""
    entry = entry_for_topic(session, topic.id)
    rooms = all_rooms(session)
    timeslots = all_timeslots(session)
    children = [H2("타임테이블 (Timetable)")]

    if not rooms or not timeslots:
        children.append(notice(
            "아직 룸/타임슬롯이 없습니다. 관리자에게 문의하세요. "
            "(No rooms/timeslots yet — contact the admin.)"
        ))
        return Section(*children, cls="schedule-section")

    if entry:
        room = next((r for r in rooms if r.id == entry.room_id), None)
        ts = session.get(Timeslot, entry.timeslot_id)
        current_label = (
            f"{room.name if room else '?'} · {ts.time_label if ts else '?'}"
        )
        children.append(notice(f"현재 배정 (Scheduled): {current_label}",
                               kind="success"))
        children.append(P("표에서 다른 빈 칸을 선택하면 자리를 변경할 수 있습니다. "
                          "(Select another open cell to move.)", cls="schedule-hint"))
    else:
        children.append(P("아래 표에서 원하는 빈 칸을 선택해 등록하세요. "
                          "(Select an open cell below to register.)", cls="schedule-hint"))

    children.append(_schedule_picker(session, topic, entry, rooms, timeslots))

    if entry:
        children.append(Form(
            Button("등록 취소 (Cancel registration)", type="submit", cls="danger"),
            hx_post=f"/manage/{_tok(topic)}/unschedule",
            hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
        ))
    return Section(*children, cls="schedule-section")


# 토큰을 토픽에 임시 보관해 폼 action 생성에 사용 (raw token passed via closure)
def _tok(topic: Topic) -> str:
    return getattr(topic, "_raw_token", "")


def _image_edit_fields(topic: Topic):
    """주제 대표 이미지 편집 (Edit topic image) — 현재 이미지·교체·제거."""
    children = [Legend("주제 대표 이미지 (Topic image)")]
    if topic.image_url:
        children.append(Div(
            Img(src=topic.image_url, alt="현재 이미지 (Current image)",
                cls="edit-thumb"),
            Label(
                Input(type="checkbox", name="remove_image", value="1"),
                " 사진 제거 (Remove image)", cls="checkbox-label",
            ),
            cls="current-image",
        ))
    else:
        children.append(Small("아직 등록된 이미지가 없습니다. (No image yet.)",
                              cls="field-help"))
    children += [
        Div(
            Label("새 파일 업로드 (Upload new)", fr="m-image_file"),
            Input(id="m-image_file", name="image_file", type="file",
                  accept="image/png,image/jpeg,image/gif,image/webp"),
            cls="field",
        ),
        Div(
            Label("또는 이미지 URL (or Image URL)", fr="m-image_url"),
            Input(id="m-image_url", name="image_url", type="url", required=False,
                  placeholder="https://example.com/cover.png"),
            cls="field",
        ),
    ]
    return Fieldset(*children, cls="image-fields")


def _panel(session, topic: Topic, *, msg=None):
    """관리 패널 (Manage panel) — HTMX swap 대상."""
    tok = _tok(topic)
    children = [H1("내 주제 관리 (Manage My Topic)")]
    if msg:
        # 화면에 떠서 슬라이드 인 + 자동 사라짐 — 스크롤 위치와 무관하게 눈에 띔
        children.append(Div(msg, cls="manage-toast", aria_live="polite"))
    edit_form = Form(
        field("주제 제목 (Topic Title)", "title", value=topic.title),
        field("설명 (Description)", "description", value=topic.description,
              textarea=True, required=False),
        _image_edit_fields(topic),
        Button("저장 (Save)", type="submit"),
        hx_post=f"/manage/{tok}/edit", hx_encoding="multipart/form-data",
        hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
    )
    delete_form = Form(
        Button("주제 삭제 (Delete topic)", type="submit", cls="danger"),
        hx_post=f"/manage/{tok}/delete",
        hx_confirm="정말 삭제하시겠습니까? (Delete this topic?)",
        hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
    )
    children += [
        Section(H2("주제 편집 (Edit Topic)"), edit_form, cls="edit-section"),
        _schedule_section(session, topic),
        Section(H2("삭제 (Delete)"), delete_form, cls="delete-section"),
    ]
    return Div(*children, id=PANEL_ID, cls="manage-panel")


def register(app) -> None:
    # ---- 로그인 기반 '내 주제 수정' 진입 (Login-based entry, no token in URL) ----
    @app.get("/manage")
    def manage_login():
        # 숨은 폼: 로그인 확인되면 JS가 이메일을 채워 자동 제출한다.
        resolve = Form(
            Input(type="hidden", id="manage-email", name="email"),
            id="manage-resolve", method="post", action="/manage/open",
        )
        gate = P("PyCon 로그인 확인 중… (Checking your PyCon login…)",
                 id="manage-gate", cls="notice notice-info", role="status")
        return layout(
            "내 주제 수정 (Edit My Topic)",
            H1("내 주제 수정 (Edit My Topic)"),
            gate, resolve,
            Script(_MANAGE_LOGIN_JS),
            active="/manage",
        )

    @app.post("/manage/open")
    def manage_open(email: str = ""):
        email = (email or "").strip()
        if not email:
            return RedirectResponse(PYCON_SIGNIN_URL, status_code=303)
        with get_session() as session:
            topics = _topics_for_email(session, email)
            if not topics:
                return layout(
                    "내 주제 수정 (Edit My Topic)",
                    H1("내 주제 수정 (Edit My Topic)"),
                    notice(f"'{email}' 으로 등록된 주제가 없습니다. "
                           "(No topics found for this email.)"),
                    A("주제 등록하기 (Submit a topic)", href="/topics/new", cls="btn"),
                    active="/manage",
                )
            if len(topics) == 1:
                raw = _issue_token(session, topics[0])
                return RedirectResponse(f"/manage/{raw}?sent=1", status_code=303)
            # 여러 개면 어떤 주제를 수정할지 고른다 (multiple → choose one).
            choices = [
                Form(
                    Input(type="hidden", name="email", value=email),
                    Input(type="hidden", name="topic_id", value=str(t.id)),
                    Button(t.title, type="submit", cls="btn secondary"),
                    method="post", action="/manage/open-one", cls="manage-pick",
                ) for t in topics
            ]
            return layout(
                "내 주제 수정 (Edit My Topic)",
                H1("어떤 주제를 수정할까요? (Which topic?)"),
                notice(f"{email} 으로 등록된 주제 {len(topics)}개입니다. 하나를 고르세요."),
                *choices,
                active="/manage",
            )

    @app.post("/manage/open-one")
    def manage_open_one(topic_id: int = 0, email: str = ""):
        email = (email or "").strip().lower()
        with get_session() as session:
            topic = session.get(Topic, topic_id)
            if (topic and topic.deleted_at is None
                    and (topic.host_email or "").strip().lower() == email):
                raw = _issue_token(session, topic)
                return RedirectResponse(f"/manage/{raw}?sent=1", status_code=303)
        return RedirectResponse("/manage", status_code=303)

    @app.get("/manage/{token}")
    def manage(token: str, sent: str = ""):
        with get_session() as session:
            topic = _load_topic(session, token)
            if not topic:
                return layout(
                    "유효하지 않은 링크 (Invalid link)",
                    notice("링크가 유효하지 않거나 만료되었습니다. "
                           "(This link is invalid or expired.)", kind="error"),
                    A("홈으로 (Home)", href="/", cls="btn secondary"),
                )
            topic._raw_token = token
            # 로그인으로 진입했을 때: 매직링크도 메일로 보냈다고 한 번 안내
            msg = notice("관리용 매직링크를 이메일로도 전송했습니다. 다음에는 이메일의 "
                         "링크로 바로 접속할 수 있습니다. "
                         "(We also emailed you the magic link.)",
                         kind="success") if sent else None
            return layout("내 주제 관리 (Manage My Topic)",
                          _panel(session, topic, msg=msg))

    @app.post("/manage/{token}/edit")
    async def manage_edit(token: str, title: str, description: str = "",
                          image_url: str = "", remove_image: str = "",
                          image_file: UploadFile = None):
        with get_session() as session:
            topic = _load_topic(session, token)
            if not topic:
                return _invalid()
            topic._raw_token = token
            title = (title or "").strip()
            if not title:
                return _panel(session, topic,
                              msg=notice("제목은 필수입니다. (Title required.)",
                                         kind="error"))

            # 이미지: 새 업로드 > 새 URL > 제거 > 유지 (upload > url > remove > keep)
            try:
                stored = await save_image(image_file)
                new_url = stored or normalize_image_url(image_url)
            except UploadError as exc:
                return _panel(session, topic,
                              msg=notice(str(exc), kind="error"))
            old_url = topic.image_url
            if new_url:
                topic.image_url = new_url
                if old_url and old_url != new_url:
                    delete_local_image(old_url)
            elif remove_image:
                topic.image_url = None
                delete_local_image(old_url)

            topic.title = title
            topic.description = (description or "").strip()
            topic.updated_at = utcnow()
            session.add(topic)
            session.commit()
            session.refresh(topic)
            topic._raw_token = token
            return _panel(session, topic,
                          msg=notice("저장되었습니다. (Saved.)", kind="success"))

    @app.post("/manage/{token}/delete")
    def manage_delete(token: str):
        with get_session() as session:
            topic = _load_topic(session, token)
            if not topic:
                return _invalid()
            # 스케줄 해제 후 소프트 삭제 (free slot, then soft-delete)
            entry = entry_for_topic(session, topic.id)
            if entry:
                session.delete(entry)
            topic.deleted_at = utcnow()
            topic.updated_at = utcnow()
            session.add(topic)
            session.commit()
        return Div(
            H1("삭제되었습니다 (Topic deleted)"),
            notice("주제가 삭제되었습니다. (Your topic has been deleted.)",
                   kind="success"),
            A("홈으로 (Home)", href="/", cls="btn secondary"),
            id=PANEL_ID, cls="manage-panel",
        )

    @app.post("/manage/{token}/schedule")
    def manage_schedule(token: str, slot: str):
        with get_session() as session:
            topic = _load_topic(session, token)
            if not topic:
                return _invalid()
            topic._raw_token = token
            try:
                room_id, ts_id = (int(x) for x in slot.split(":"))
            except (ValueError, AttributeError):
                return _panel(session, topic,
                              msg=notice("슬롯 선택이 올바르지 않습니다. (Invalid slot.)",
                                         kind="error"))
            entry = entry_for_topic(session, topic.id)
            try:
                if entry:
                    entry.room_id = room_id
                    entry.timeslot_id = ts_id
                    entry.updated_at = utcnow()
                    session.add(entry)
                else:
                    session.add(ScheduleEntry(
                        topic_id=topic.id, room_id=room_id, timeslot_id=ts_id))
                session.commit()
            except IntegrityError:
                session.rollback()
                topic._raw_token = token
                return _panel(session, topic, msg=notice(
                    "이미 선택된 슬롯입니다. 다른 슬롯을 고르세요. "
                    "(That slot was just taken — pick another.)", kind="error"))
            topic._raw_token = token
            return _panel(session, topic,
                          msg=notice("타임테이블에 등록되었습니다. (Scheduled.)",
                                     kind="success"))

    @app.post("/manage/{token}/unschedule")
    def manage_unschedule(token: str):
        with get_session() as session:
            topic = _load_topic(session, token)
            if not topic:
                return _invalid()
            entry = entry_for_topic(session, topic.id)
            if entry:
                session.delete(entry)
                session.commit()
            topic._raw_token = token
            return _panel(session, topic,
                          msg=notice("등록이 취소되었습니다. (Registration cancelled.)",
                                     kind="success"))


def _invalid():
    return Div(
        notice("링크가 유효하지 않습니다. (Invalid link.)", kind="error"),
        id=PANEL_ID, cls="manage-panel",
    )
