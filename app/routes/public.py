"""공개 페이지 (Public pages): /, /topics, /topics/new, /schedule, /board, /board2."""
from __future__ import annotations

import json

from fasthtml.common import (
    A,
    Article,
    Aside,
    Button,
    Div,
    Footer,
    Form,
    H1,
    H2,
    Header,
    Iframe,
    Img,
    Input,
    Label,
    P,
    Script,
    Section,
    Span,
    Table,
    Td,
    Th,
    Thead,
    Tr,
)
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import UploadFile

from ..components import (
    account_field,
    board_language_auto_switch,
    day_caption,
    date_tabs,
    fmt_day_short,
    layout,
    notice,
    schedule_table,
    topic_card,
    topic_text_fields,
)
from ..auth import (
    Identity,
    clear_identity,
    identity_from_session,
    is_admin_email,
    login_required,
    login_required_page,
    note_identity,
    resolve_identity,
    set_identity,
)
from ..config import get_settings
from ..database import get_session
from ..i18n import get_lang, normalize_lang, set_lang, t
from ..models import ScheduleEntry, Timeslot, Topic, TopicKind, utcnow
from ..queries import (
    active_topics,
    all_rooms,
    all_timeslots,
    board_qrs,
    board_language_interval,
    auto_board_urls,
    entry_for_topic,
    events_by_timeslot,
    get_owned_topic,
    is_scheduling_open,
    schedule_map,
    room_slot_closures,
    scroll_board_url,
    scheduling_opens_on,
    topics_by_id,
    topics_for_owner,
)
from ..uploads import UploadError, normalize_image_url, save_image


# 입력값을 카드 미리보기에 실시간 반영 (Mirror form inputs into the pinned card)
# 한국어-only placeholder 들은 렌더 시점에 t() 로 주입(%s) — _live_preview_js() 참고.
_LIVE_PREVIEW_JS = """
(function () {
  var map = [
    ['f-title', 'pv-title', '%s'],
    ['f-description', 'pv-desc', '%s'],
    ['f-host_name', 'pv-host', '%s']
  ];
  function syncText() {
    for (var i = 0; i < map.length; i++) {
      var src = document.getElementById(map[i][0]);
      var dst = document.getElementById(map[i][1]);
      if (!src || !dst) continue;
      var v = (src.value || '').trim();
      dst.textContent = v || map[i][2];
      dst.classList.toggle('is-empty', !v);
    }
  }
  function showImage(url) {
    var fig = document.getElementById('pv-figure');
    var img = document.getElementById('pv-image');
    if (!fig || !img) return;
    if (url) { img.src = url; fig.hidden = false; }
    else { img.removeAttribute('src'); fig.hidden = true; }
  }
  function syncImage() {
    var fileInput = document.getElementById('f-image_file');
    var urlInput = document.getElementById('f-image_url');
    if (fileInput && fileInput.files && fileInput.files[0]) {
      var reader = new FileReader();
      reader.onload = function (e) { showImage(e.target.result); };
      reader.readAsDataURL(fileInput.files[0]);
    } else if (urlInput && urlInput.value.trim()) {
      showImage(urlInput.value.trim());
    } else {
      showImage('');
    }
  }
  document.addEventListener('input', function (e) {
    syncText();
    if (e.target && (e.target.id === 'f-image_url' || e.target.id === 'f-image_file')) {
      syncImage();
    }
  });
  document.addEventListener('change', function (e) {
    if (e.target && e.target.id === 'f-image_file') syncImage();
  });
  syncText();
})();
"""


# 프로그램 소개는 운영 중에도 전광판의 스크롤 대상(/scroll-board)으로 바로 쓸 수 있는
# 고정 안내 페이지다. 외부 링크 주소가 확정되지 않은 항목은 문구만 우선 노출한다.
PROGRAMS = (
    {
        "title": "열린 공간",
        "when": "8/15(토) ~ 16(일) 13:30 ~ 17:10 (예정) (KST)",
        "venue": "원흥관 3층 I-Space",
        "link_label": "열린 공간 전자게시판",
        "link_url": "/topics",
        "description": "열린공간은 파이콘 참가자들이 사전 또는 현장에서 자유롭게 주제를 정해, 1시간 동안 함께 모이는 자율 모임입니다. 기술 토론부터 보드게임, 요가, 산책 같은 가벼운 활동까지 누구나 직접 만들고 참여할 수 있는 네트워킹 프로그램입니다.",
    },
    {
        "title": "저글링",
        "when": "8/15(토) ~ 16(일) (KST)",
        "venue": "추후 공개 (공이 어디로 튈지 모르듯, 장소도 아직 미정입니다 🎾)",
        "link_label": "파이콘 US 저글링",
        "description": "코딩도 잠깐 내려두고, 이번엔 공을 올려보세요! 저글링은 생각보다 어렵고, 생각보다 재밌습니다. 잘 못해도 괜찮아요 — 실패해도 try again하면 되니까요. 🔄",
    },
    {
        "title": "작품 전시전",
        "when": "8/15(토) ~ 16(일) (KST)",
        "venue": "신공학관 3106호",
        "link_label": "작품 전시전 모집폼 (~7/25.토)",
        "description": "간단한 콘솔 앱부터 라이브러리, 업무 자동화 도구, 챗봇 등등 파이썬으로 만든 것이라면 무엇이든 선보일 수 있는 절호의 기회! 파이썬으로 뚝딱뚝딱 만든 소중한 작품과 경험을 나누고 자랑할 수 있는 '파이썬 작품 전시전'입니다.",
    },
    {
        "title": "파이콘 네임월",
        "when": "8/15(토) ~ 16(일) (KST)",
        "venue": "신공학관 7층 (원흥관 연결 통로)",
        "description": "참가자 여러분의 이름이 모여, 올해의 파이콘 한국이 되었습니다. 우리가 함께 그린 파이콘 한국 속에서 본인의 이름을 찾아보세요!",
        "note": "7/31.(금)까지 등록한 일반 티켓, 개인 후원 티켓, 기업 후원 티켓, 학생 티켓, 후원사 티켓 참가자만 해당되는 이벤트입니다.",
    },
    {
        "title": "파이펀 퀴즈",
        "when": "8/15(토) ~ 16(일) 11:40 ~ 12:00 (KST)",
        "venue": "신공학관 4층 4142호 (대강당)",
        "description": "점심 시간 4142호로! 코딩 몰라도 파이썬에 관심있는 누구나 참여 가능한 20분 컷 PyFun 퀴즈쇼",
        "note": "파이콘 참여자 누구나!",
    },
    {
        "title": "파이북",
        "when": "8/15(토) ~ 16(일) 11:40 ~ 12:00 (KST)",
        "venue": "신공학관 4층 4147호",
        "description": "도서 감상평을 작성하고 책을 받아가세요! 도서를 선택하여 태그와 함께 SNS에 감상평을 게시하거나 손글씨 감상평을 작성해주세요. 서로의 책에 대한 소개와 소감을 나누며 마무리됩니다.",
        "note": "파이콘 참여자 누구나! 선착순으로 진행되며 조기마감될 수 있습니다.",
    },
)


def _live_preview_js() -> str:
    """카드 미리보기 JS (요청 언어로 placeholder 채움)."""
    return _LIVE_PREVIEW_JS % (
        t("제목을 입력하세요", "Enter a title"),
        t("설명을 입력하세요", "Enter a description"),
        t("익명", "Anonymous"),
    )


def _new_error(message: str):
    """주제 등록 오류 안내 (Submission error page)."""
    return layout(
        t("주제 등록", "Submit Topic"),
        notice(message, kind="error"),
        A(t("돌아가기", "Back"), href="/topics/new", cls="btn secondary"),
        active="/topics/new",
    )


def _kind_field():
    """주제 유형 선택 (Topic type) — 대화/이벤트, 등록 시 1회 고정.

    '주제 대표 이미지'와 같은 Fieldset/Legend 박스 형식, 라디오는 가로 배치.
    """
    from fasthtml.common import Fieldset, Legend

    def opt(value, label, checked=False):
        return Label(
            Input(type="radio", name="kind", value=value, checked=checked),
            Span(label, cls="kind-name"),
            cls="kind-option",
        )

    return Fieldset(
        Legend(t("주제 유형", "Topic type")),
        Div(
            opt("conversation", t("대화", "Conversation"), checked=True),
            opt("event", t("이벤트", "Event")),
            cls="kind-options",
        ),
        cls="image-fields",  # '주제 대표 이미지'와 동일한 박스 스타일 재사용
    )


def _image_fields():
    """주제 대표 이미지 입력 (Topic image) — 업로드 또는 URL 둘 다 지원."""
    from fasthtml.common import Fieldset, Legend, Small

    return Fieldset(
        Legend(t("주제 대표 이미지", "Topic image")),
        Small(t("주제를 대표하는 이미지를 업로드하거나 이미지 URL을 입력하세요. (선택)",
                "Upload an image file or enter an image URL — optional."),
              cls="field-help"),
        Div(
            Label(t("파일 업로드", "Upload"), fr="f-image_file"),
            Input(id="f-image_file", name="image_file", type="file",
                  accept="image/png,image/jpeg,image/gif,image/webp"),
            cls="field",
        ),
        Div(
            Label(t("또는 이미지 URL", "or Image URL"), fr="f-image_url"),
            Input(id="f-image_url", name="image_url", type="url", required=False,
                  placeholder="https://example.com/cover.png"),
            cls="field",
        ),
        cls="image-fields",
    )


def _new_topic_view(identity, anchor_id: str = "new") -> list:
    """주제 등록 폼 + 실시간 프리뷰 뷰 (Topic-submission form view).

    이메일·pycon_id 는 신원에서 공급하므로 폼에 두지 않는다. `/topics/new` 전용.
    """
    hero = Header(
        H1(Span(t("함께 이야기할", "Propose a topic")),
           Span(t("주제를 제안하세요", "to discuss together")), cls="hero-title"),
        P(t("열린공간(OpenSpace)은 정해진 발표 대신 참가자가 직접 이야기하고 싶은 주제를 "
            "제안하고 함께 토론하는 자리입니다. 제안한 주제는 행사 이틀 전 열리는 "
            "타임테이블에서 원하는 시간·장소에 직접 등록할 수 있습니다.",
            "OpenSpace is an unconference where participants propose the topics they "
            "want to discuss — instead of a fixed program. You then place your topic "
            "into the timetable yourself, which opens two days before the event."),
          cls="hero-lede"),
        id=anchor_id, cls="page-hero",
    )
    form = Form(
        account_field(identity.email),
        _kind_field(),
        *topic_text_fields(),
        _image_fields(),
        Button(t("주제 등록", "Submit"), type="submit", cls="btn btn-pin"),
        P(t("등록 후에는 'MY(내 주제)'에서 수정하거나 타임테이블에 자리를 잡을 수 있어요.",
            "After submitting, manage it or place it on the timetable from 'My topics'."),
          cls="form-hint"),
        method="post", action="/topics/new", enctype="multipart/form-data",
        cls="topic-form",
    )
    preview = Aside(
        Div(cls="pin"),
        Article(
            Span(t("미리보기", "Preview"), cls="card-eyebrow"),
            Div(
                Img(id="pv-image",
                    alt=t("주제 대표 이미지 미리보기", "Topic image preview")),
                id="pv-figure", cls="card-figure", hidden=True,
            ),
            H2(t("제목을 입력하세요", "Enter a title"),
               id="pv-title", cls="card-title is-empty"),
            P(t("설명을 입력하세요", "Enter a description"), id="pv-desc",
              cls="card-desc is-empty"),
            Footer(
                Span(t("제안자", "Host"), cls="card-host-label"),
                Span(t("익명", "Anonymous"), id="pv-host",
                     cls="card-host is-empty"),
                cls="card-foot",
            ),
            cls="pin-card",
        ),
        cls="pin-preview", aria_hidden="true",
    )
    return [
        hero,
        Div(Section(form, cls="form-col"), preview, cls="new-grid", id="new-grid"),
        Script(_live_preview_js()),
    ]


def _my_topics_view(topics):
    """MY '내 주제' 리스트뷰 (My-topics list) — 주제 클릭 → 관리 페이지(신원 소유)."""
    rows = [
        A(tp.title, href=f"/manage/{tp.id}", cls="btn secondary manage-pick")
        for tp in topics
    ]
    return Section(
        H2(t("내 주제", "My topics")),
        P(t("등록한 주제를 눌러 수정·일정 관리로 들어갈 수 있어요.",
            "Tap a topic to edit it or manage its schedule."), cls="form-hint"),
        *rows,
        A(t("주제 등록", "Submit a topic"), href="/", cls="btn"),
        cls="my-topics-list",
    )


# ---- 타임테이블에서 직접 자리 잡기 (Interactive scheduling on /schedule) ----
SCHED_ID = "sched-interactive"


def _sched_slot_cell(tid, room, ts, entry, current_entry, *, schedulable,
                     topics, closures, mine_title="", mine_description=""):
    """타임테이블 한 칸 — 내 자리/사용 중/빈 칸. 빈 칸은 눌러 등록·이동."""
    is_mine = current_entry and entry and entry.id == current_entry.id
    if is_mine:
        # 내 자리엔 ✓ + 주제 제목을 표시 (어떤 주제가 잡혔는지 바로 보이게).
        label = f"✓ {mine_title}" if mine_title else t("✓ 내 주제", "✓ My topic")
        children = [Div(label, cls="slot-title", title=mine_title or None)]
        if mine_description:
            children.append(Div(mine_description, cls="slot-description"))
        return Td(*children,
                  cls="slot-mine", aria_label=t("현재 내 자리", "My current slot"))
    if entry:
        scheduled_topic = topics.get(entry.topic_id)
        if scheduled_topic:
            children = [Div(scheduled_topic.title, cls="slot-title")]
            if scheduled_topic.description:
                children.append(Div(scheduled_topic.description, cls="slot-description"))
            return Td(*children, cls="slot-taken", title=scheduled_topic.title)
        return Td(Span(t("사용 중", "Taken"), cls="slot-tag"), cls="slot-taken")
    closure = closures.get((room.id, ts.id))
    if closure:
        return Td(Span(closure.label or t("닫힘", "Closed"), cls="slot-tag"), cls="slot-closed")
    if not schedulable:
        return Td(Span(t("비어있음", "Open"), cls="slot-tag"), cls="slot-open")
    label = t("여기로 이동", "Move here") if current_entry else t("이 자리 잡기", "Take")
    return Td(
        Button(label, type="button",
               hx_post=f"/schedule/{tid}/take",
               hx_vals=f'{{"slot": "{room.id}:{ts.id}"}}',
               hx_target=f"#{SCHED_ID}", hx_swap="outerHTML", cls="slot-pick"),
        cls="slot-open",
    )


def _sched_grid(rooms, timeslots, taken, tid, current_entry, *, schedulable,
                topics, events, closures, mine_title="", mine_description=""):
    header = Tr(Th(t("시간 / 룸", "Time / Room")), *[Th(r.name) for r in rooms])
    rows = []
    for ts in timeslots:
        if ts.is_closed:
            rows.append(Tr(Th(ts.time_label, scope="row"),
                           Td(ts.closed_label, colspan=len(rooms), cls="slot-closed")))
            continue
        # 이벤트는 룸을 점유하지 않지만, 같은 시간대에 무엇이 열리는지 보여준다.
        slot_events = events.get(ts.id, [])
        for i, event_topic in enumerate(slot_events):
            event_cells = []
            if i == 0:
                event_cells.append(Th(ts.time_label, scope="row",
                                      rowspan=len(slot_events) + 1))
            event_children = [
                Div(Span(t("이벤트", "Event"), cls="kind-badge is-event"),
                    " ", event_topic.title, cls="slot-title"),
            ]
            if event_topic.description:
                event_children.append(Div(event_topic.description, cls="slot-description"))
            event_cells.append(Td(*event_children, colspan=len(rooms), cls="slot-event",
                                  title=event_topic.title))
            rows.append(Tr(*event_cells))

        cells = [] if slot_events else [Th(ts.time_label, scope="row")]
        for room in rooms:
            entry = taken.get((room.id, ts.id))
            cells.append(_sched_slot_cell(tid, room, ts, entry, current_entry,
                                          schedulable=schedulable,
                                          topics=topics, mine_title=mine_title,
                                          closures=closures,
                                          mine_description=mine_description))
        rows.append(Tr(*cells))
    return Div(Table(Thead(header), *rows, cls="schedule manage-schedule"),
               cls="schedule-scroll")


def _sched_event_grid(timeslots, tid, current_entry, *, schedulable):
    """이벤트(시간만)용 등록 표 — 시간대마다 전체폭 버튼 한 개.

    이벤트는 룸을 잡지 않으므로 룸 칸 대신 '이 시간에 등록' 버튼을 보여준다.
    같은 시간에 이벤트 여러 개가 가능하므로 '사용 중' 상태는 없다(내 자리만 표시).
    """
    header = Tr(Th(t("시간", "Time")), Th(t("이벤트", "Event")))
    rows = []
    for ts in timeslots:
        if ts.is_closed:
            rows.append(Tr(Th(ts.time_label, scope="row"),
                           Td(ts.closed_label, cls="slot-closed")))
            continue
        is_mine = current_entry and current_entry.timeslot_id == ts.id
        if is_mine:
            cell = Td(Span(t("✓ 내 이벤트", "✓ My event"), cls="slot-tag"),
                      cls="slot-mine",
                      aria_label=t("현재 내 자리", "My current slot"))
        elif not schedulable:
            cell = Td(Span(t("비어있음", "Open"), cls="slot-tag"), cls="slot-open")
        else:
            label = (t("여기로 이동", "Move here") if current_entry
                     else t("이 시간에 등록", "Register here"))
            cell = Td(Button(label, type="button",
                             hx_post=f"/schedule/{tid}/take",
                             hx_vals=f'{{"slot": "{ts.id}"}}',
                             hx_target=f"#{SCHED_ID}", hx_swap="outerHTML",
                             cls="slot-pick"),
                      cls="slot-open")
        rows.append(Tr(Th(ts.time_label, scope="row"), cell))
    return Div(Table(Thead(header), *rows, cls="schedule manage-schedule"),
               cls="schedule-scroll")


def _sched_interactive(db, topic, *, admin_override: bool = False):
    """내 주제 기준 인터랙티브 타임테이블 (htmx swap 대상)."""
    tid = topic.id
    entry = entry_for_topic(db, topic.id)
    rooms = all_rooms(db)
    timeslots = all_timeslots(db)
    topics = topics_by_id(db)
    events = events_by_timeslot(db)
    children = []

    # 이벤트는 룸이 없어도 시간만 있으면 등록 가능 — 룸 필요는 대화에만.
    if not timeslots or (not topic.is_event and not rooms):
        children.append(notice(t(
            "아직 룸/타임슬롯이 없습니다. 관리자에게 문의하세요.",
            "No rooms/timeslots yet — contact the admin.")))
        return Div(*children, id=SCHED_ID, cls="schedule-section")

    # 관리자는 사용자용 화면에서도 행사일 전 자가등록 제한을 우회한다.
    schedulable = admin_override or is_scheduling_open(db)
    opens_on = scheduling_opens_on(db)
    taken = schedule_map(db)
    closures = room_slot_closures(db)

    if entry:
        ts = db.get(Timeslot, entry.timeslot_id)
        if topic.is_event:
            label = ts.time_label if ts else "?"
        else:
            room = next((r for r in rooms if r.id == entry.room_id), None)
            label = f"{room.name if room else '?'} · {ts.time_label if ts else '?'}"
        children.append(notice(f"{t('현재 배정', 'Scheduled')}: {label}", kind="success"))

    if admin_override:
        children.append(P(
            t("관리자 권한으로 날짜 제한 없이 등록할 수 있습니다.",
              "Admin access: registration is available regardless of date."),
            cls="schedule-hint"))
    elif not schedulable:
        children.append(notice(
            f"{t('타임테이블 등록은 행사 이틀 전부터 열립니다.', 'Self-scheduling opens two days before the event.')}"
            f" {t('등록 시작', 'Opens')}: {opens_on}", kind="info"))
    elif entry:
        children.append(P(t("표에서 다른 빈 칸을 선택하면 자리를 변경할 수 있습니다.",
                            "Select another open cell to move."), cls="schedule-hint"))
    else:
        children.append(P(t("아래 표에서 원하는 빈 칸을 선택해 등록하세요.",
                            "Select an open cell below to register."), cls="schedule-hint"))

    days = sorted({ts.starts_at.date().isoformat() for ts in timeslots})
    default_day = None
    if entry:
        cur_ts = db.get(Timeslot, entry.timeslot_id)
        if cur_ts:
            default_day = cur_ts.starts_at.date().isoformat()

    def render_day(day: str):
        day_slots = [ts for ts in timeslots
                     if ts.starts_at.date().isoformat() == day]
        if topic.is_event:
            return _sched_event_grid(day_slots, tid, entry,
                                     schedulable=schedulable)
        return _sched_grid(rooms, day_slots, taken, tid, entry,
                           schedulable=schedulable, topics=topics, events=events, closures=closures,
                           mine_title=topic.title, mine_description=topic.description)

    children.append(date_tabs(days, render_day, id_prefix="sday-i",
                              default_day=default_day))

    if entry:
        children.append(Form(
            Button(t("등록 취소", "Cancel registration"), type="submit", cls="danger"),
            hx_post=f"/schedule/{tid}/cancel",
            hx_target=f"#{SCHED_ID}", hx_swap="outerHTML"))
    return Div(*children, id=SCHED_ID, cls="schedule-section")


def _owner_schedule_area(db, my_topics, selected_id, *, admin_override: bool = False):
    """로그인 소유자용 영역 — 내 주제 칩 + 선택 주제의 인터랙티브 표.

    칩을 누르면 그 주제로 표가 활성화(빈 칸 클릭 가능)된다. 페이지 이동 없이
    HTMX 로 이 영역(#sched-owner)만 교체한다.
    """
    selected = next((m for m in my_topics if m.id == selected_id), my_topics[0])
    chips = [
        Button(tp.title, type="button",
               hx_get=f"/schedule/own?topic={tp.id}",
               hx_target="#sched-owner", hx_swap="outerHTML",
               cls="btn" if tp.id == selected.id else "btn secondary")
        for tp in my_topics
    ]
    # 현재 자리 잡는 주제 이름을 강조 표시 (selected topic name).
    heading = P(
        Span(t("자리 잡을 주제: ", "Placing: "), cls="sched-pick-label"),
        Span(selected.title, cls="sched-pick-name"),
        cls="sched-pick",
    )
    hint = (t("아래 칩으로 주제를 바꿀 수 있어요. 빈 칸을 누르면 자리가 잡혀요.",
              "Switch topic with the chips below. Click an open cell to place it.")
            if len(my_topics) > 1 else
            t("빈 칸을 눌러 자리를 잡으세요.", "Click an open cell to place it."))
    return Div(
        heading,
        P(selected.description or t("(설명 없음)", "(No description)"), cls="sched-pick-desc"),
        P(hint, cls="form-hint"),
        Div(*chips, cls="sched-chips") if len(my_topics) > 1 else None,
        _sched_interactive(db, selected, admin_override=admin_override),
        id="sched-owner",
    )


def _safe_next(nxt: str | None) -> str:
    """오픈 리다이렉트 방지 (Prevent open redirect) — 로컬 경로만 허용."""
    # '//' 와 '/\' (일부 브라우저가 // 로 정규화) 모두 차단.
    if nxt and nxt.startswith("/") and not nxt.startswith(("//", "/\\")):
        return nxt
    return "/"


def register(app) -> None:
    @app.get("/lang/{code}")
    def set_language(code: str, req):
        # 언어 쿠키 저장 후 원래 페이지로 (set lang cookie, then back)
        from starlette.responses import RedirectResponse

        nxt = _safe_next(req.query_params.get("next"))
        resp = RedirectResponse(nxt, status_code=303)
        resp.set_cookie(
            "lang", normalize_lang(code),
            max_age=60 * 60 * 24 * 365, samesite="lax",
        )
        return resp

    @app.get("/auth/check")
    def auth_check(request, session):
        # 로그인 게이트의 새 창 로그인 완료 확인 프로브 (서버측 PyCon 세션 검증).
        from starlette.responses import JSONResponse

        identity = resolve_identity(request, session)
        return JSONResponse({"authed": identity is not None})

    @app.post("/dev/login")
    def dev_login(session, email: str = "", pycon_id: int = 0):
        # 개발/테스트 전용 수기 로그인 — 운영(pycon.kr)에선 비활성.
        import hashlib

        from starlette.responses import RedirectResponse

        if not get_settings().dev_login_enabled:
            return RedirectResponse("/", status_code=303)
        email = (email or "").strip()
        if email:
            pid = int(pycon_id or 0)
            if pid <= 0:
                # 이메일에서 '안정적'으로 회원 id 생성 (서버 재시작과 무관, 이메일별 고유).
                digest = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()
                pid = int(digest[:8], 16) % 1_000_000 + 1
            set_identity(session, Identity(
                pycon_id=pid, email=email, username=email.split("@")[0]))
        return RedirectResponse("/", status_code=303)

    @app.post("/logout")
    def logout(session):
        from starlette.responses import RedirectResponse

        clear_identity(session)
        return RedirectResponse("/", status_code=303)

    @app.get("/")
    def home(request, session):
        # 홈 = 주제 등록(첫 화면). 신원 필요. 내 주제 관리는 /my 로 분리.
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        return layout(
            t("주제 등록", "Submit Topic"),
            *_new_topic_view(identity),
            active="/", main_cls="content page-new",
        )

    @app.get("/my")
    def my_topics_page(request, session):
        # MY = 내 주제 대시보드. 신원으로 내 주제 목록을 보여준다.
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        with get_session() as db:
            topics = topics_for_owner(db, identity)
        greeting = P(
            f"{t('안녕하세요', 'Hi')}, {identity.username or identity.email}! "
            f"({identity.email})", cls="form-hint")
        if topics:
            body = _my_topics_view(topics)
        else:
            body = Section(
                P(t("아직 등록한 주제가 없어요. 첫 주제를 제안해 보세요!",
                    "No topics yet — propose your first one!"), cls="form-hint"),
                A(t("주제 등록", "Submit a topic"), href="/", cls="btn"),
                cls="my-topics-list",
            )
        return layout(
            t("내 주제", "MY"),
            H1(t("내 주제", "My topics")),
            greeting,
            body,
            active="/my",
        )

    @app.get("/topics")
    def topics_list(session):
        # nav 관리자 탭을 위해 세션 캐시 신원을 반영(익명엔 외부 호출 없음).
        note_identity(identity_from_session(session))
        with get_session() as db:
            topics = active_topics(db)
            slots = schedule_map(db)
            # topic_id -> (정렬 시각, 테이블 순서, 배정 정보)
            rooms = {r.id: r for r in all_rooms(db)}
            timeslots = {t.id: t for t in all_timeslots(db)}
            scheduled: dict[int, tuple[datetime, int, str]] = {}
            for (room_id, ts_id), entry in slots.items():
                room = rooms.get(room_id)
                ts = timeslots.get(ts_id)
                if room and ts:
                    scheduled[entry.topic_id] = (
                        ts.starts_at,
                        room.sort_order,
                        f"{ts.starts_at:%Y.%m.%d} · {ts.time_label} · {room.name}",
                    )
            # 시간만 배정하는 이벤트도 배정된 주제로 취급해 날짜·시간 순으로 함께 표시.
            for ts_id, event_topics in events_by_timeslot(db).items():
                ts = timeslots.get(ts_id)
                if ts:
                    for event_topic in event_topics:
                        scheduled[event_topic.id] = (
                            ts.starts_at,
                            -1,
                            f"{ts.starts_at:%Y.%m.%d} · {ts.time_label} · {t('이벤트', 'Event')}",
                        )

            # 배정된 주제 우선 → 날짜 → 시간 → 테이블 순. 미배정 주제는 기존 생성순 유지.
            indexed_topics = list(enumerate(topics))
            indexed_topics.sort(key=lambda item: (
                0, scheduled[item[1].id][0], scheduled[item[1].id][1], item[1].id
            ) if item[1].id in scheduled else (1, item[0], 0, 0))
            topics = [topic for _, topic in indexed_topics]

            cards = [
                topic_card(tp, scheduled_label=(
                    f"{t('배정됨', 'Scheduled')}: {scheduled[tp.id][2]}"
                    if tp.id in scheduled else None
                ))
                for tp in topics
            ]
        body = cards if cards else [
            notice(t("아직 제안된 주제가 없습니다.", "No topics yet."))]
        return layout(
            t("주제 목록", "Topic List"),
            H1(t("주제 목록", "Topic List")),
            A(t("주제 등록", "Submit Topic"), href="/", cls="btn"),
            Section(*body, cls="topic-grid"),
        )

    @app.get("/programs")
    def programs_page(session):
        # nav 관리자 탭을 위해 세션 캐시 신원을 반영한다.
        note_identity(identity_from_session(session))
        cards = []
        for program in PROGRAMS:
            related = None
            if program.get("link_url"):
                related = P(
                    Span("관련 링크: ", cls="program-label"),
                    A(program["link_label"], href=program["link_url"], cls="program-link"),
                    cls="program-related",
                )
            elif program.get("link_label"):
                related = P(
                    Span("관련 링크: ", cls="program-label"),
                    Span(program["link_label"]),
                    cls="program-related",
                )
            cards.append(Article(
                H2(program["title"]),
                Div(
                    P(Span("운영시간", cls="program-label"), program["when"]),
                    P(Span("장소", cls="program-label"), program["venue"]),
                    cls="program-meta",
                ),
                related,
                P(program["description"], cls="program-description"),
                P(program["note"], cls="program-note") if program.get("note") else None,
                cls="program-card",
            ))
        return layout(
            "프로그램 소개",
            Section(
                H1("프로그램 소개"),
                P("PyCon Korea 2026에서 함께 즐길 수 있는 프로그램을 소개합니다.",
                  cls="program-lede"),
                cls="program-intro",
            ),
            Section(*cards, cls="program-grid"),
            active="/programs",
            main_cls="content programs-page",
        )

    @app.get("/topics/new")
    def topic_new_form():
        # 주제 등록 폼은 이제 홈(/)에 있다 — 옛 경로는 홈으로 보낸다.
        from starlette.responses import RedirectResponse

        return RedirectResponse("/", status_code=303)

    @app.post("/topics/new")
    async def topic_create(request, session, title: str, host_name: str = "",
                           description: str = "", image_url: str = "",
                           kind: str = "conversation",
                           image_file: UploadFile = None):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        host_name = (host_name or "").strip()
        title = (title or "").strip()
        # 유형 화이트리스트 — 알 수 없는 값은 대화로 폴백.
        topic_kind = (TopicKind.EVENT if kind == "event"
                      else TopicKind.CONVERSATION)
        # 제목만 필수, 별명은 선택. 이메일·소유권은 신원에서 공급.
        if not title:
            return _new_error(t("제목은 필수입니다.", "Title is required."))

        # 이미지: 업로드 우선, 없으면 URL (uploaded file wins, else pasted URL)
        try:
            stored = await save_image(image_file)
            final_image = stored or normalize_image_url(image_url)
        except UploadError as exc:
            return _new_error(str(exc))

        with get_session() as db:
            topic = Topic(
                title=title,
                description=(description or "").strip(),
                host_name=host_name,
                host_email=identity.email,
                host_pycon_id=identity.pycon_id,
                host_username=identity.username,
                image_url=final_image,
                kind=topic_kind,
            )
            db.add(topic)
            db.commit()
            db.refresh(topic)

        return layout(
            t("등록 완료", "Submitted"),
            H1(t("주제가 등록되었습니다!", "Topic submitted!")),
            notice(t("내 주제에서 언제든 수정하거나 타임테이블에 자리를 잡을 수 있어요.",
                     "Edit it or place it on the timetable anytime from My topics."),
                   kind="success"),
            A(t("내 주제 보기", "View my topics"), href="/my", cls="btn"),
            " ",
            A(t("주제 또 등록", "Submit another"), href="/", cls="btn secondary"),
        )

    @app.get("/schedule")
    def schedule(request, session, topic: int = 0):
        # 한 페이지에서 처리: 익명/주제 없음 → 읽기 전용, 로그인 소유자 → 같은 페이지에
        # 내 주제 칩 + 인터랙티브 표(빈 칸 클릭=자리 잡기). 익명에 PyCon 호출이 안 가도록
        # 세션 캐시 신원만 본다(공개 안전).
        identity = identity_from_session(session)
        note_identity(identity)

        if identity:
            with get_session() as db:
                mine = topics_for_owner(db, identity)
                if mine:
                    selected = topic if any(m.id == topic for m in mine) else mine[0].id
                    return layout(
                        t("타임테이블", "Timetable"),
                        H1(t("타임테이블", "Timetable"), id="sched"),
                        _owner_schedule_area(db, mine, selected,
                                             admin_override=is_admin_email(identity)),
                        active="/schedule",
                    )

        # 공개 읽기 전용 (anon / 주제 없음)
        with get_session() as db:
            rooms = all_rooms(db)
            timeslots = all_timeslots(db)
            slots = schedule_map(db)
            closures = room_slot_closures(db)
            topics = topics_by_id(db)
            events = events_by_timeslot(db)
        if not rooms or not timeslots:
            body = schedule_table(rooms, timeslots, slots, topics, events=events,
                                  room_closures=closures,
                                  show_descriptions=True)
        else:
            days = sorted({ts.starts_at.date().isoformat() for ts in timeslots})

            def render_day(day: str):
                day_ts = [ts for ts in timeslots
                          if ts.starts_at.date().isoformat() == day]
                return schedule_table(rooms, day_ts, slots, topics, events=events,
                                      room_closures=closures,
                                      show_descriptions=True)

            body = date_tabs(days, render_day, id_prefix="sday")
        return layout(
            t("타임테이블", "Timetable"),
            H1(t("타임테이블", "Timetable")),
            body,
            active="/schedule",
        )

    @app.get("/schedule/own")
    def schedule_own(request, session, topic: int = 0):
        # 칩 클릭 시 호출되는 HTMX 파셜 — 선택 주제로 영역(#sched-owner)을 교체.
        identity = identity_from_session(session)
        if not identity:
            return login_required(request, "/")
        with get_session() as db:
            mine = topics_for_owner(db, identity)
            if not mine:
                return Div(notice(t("등록한 주제가 없습니다.", "No topics yet."),
                                  kind="error"), id="sched-owner")
            selected = topic if any(m.id == topic for m in mine) else mine[0].id
            return _owner_schedule_area(db, mine, selected,
                                        admin_override=is_admin_email(identity))

    @app.post("/schedule/{topic_id}/take")
    def schedule_take(request, session, topic_id: int, slot: str = ""):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required(request, "/")
        with get_session() as db:
            topic = get_owned_topic(db, topic_id, identity)
            if not topic:
                return Div(notice(t("접근 권한이 없습니다.", "No access."),
                                  kind="error"), id=SCHED_ID)
            admin_override = is_admin_email(identity)
            if not admin_override and not is_scheduling_open(db):
                opens_on = scheduling_opens_on(db)
                msg = (t("타임테이블 등록은 행사 이틀 전부터 열립니다.",
                         "Self-scheduling opens two days before the event.")
                       + (f" {t('등록 시작', 'Opens')}: {opens_on}" if opens_on else ""))
                return Div(notice(msg, kind="error"),
                           _sched_interactive(db, topic, admin_override=admin_override))
            try:
                if topic.is_event:
                    # 이벤트는 시간만 — slot 은 timeslot id 단독, 룸은 없음.
                    room_id, ts_id = None, int(slot)
                else:
                    room_id, ts_id = (int(x) for x in slot.split(":"))
            except (ValueError, AttributeError):
                return Div(notice(t("슬롯 선택이 올바르지 않습니다.", "Invalid slot."),
                                  kind="error"), _sched_interactive(
                                      db, topic, admin_override=admin_override))
            entry = entry_for_topic(db, topic.id)
            if room_id is not None and (room_id, ts_id) in room_slot_closures(db):
                return Div(notice(t("이 룸의 해당 시간은 닫혀 있습니다.",
                                   "This room is closed at that time."), kind="error"),
                           _sched_interactive(db, topic, admin_override=admin_override))
            try:
                if entry:
                    entry.room_id, entry.timeslot_id = room_id, ts_id
                    entry.updated_at = utcnow()
                    db.add(entry)
                else:
                    db.add(ScheduleEntry(topic_id=topic.id, room_id=room_id,
                                         timeslot_id=ts_id))
                db.commit()
            except IntegrityError:
                db.rollback()
                return Div(notice(t("이미 선택된 슬롯입니다. 다른 슬롯을 고르세요.",
                                    "That slot was just taken — pick another."),
                                  kind="error"),
                           _sched_interactive(db, topic, admin_override=admin_override))
            return _sched_interactive(db, topic, admin_override=admin_override)

    @app.post("/schedule/{topic_id}/cancel")
    def schedule_cancel(request, session, topic_id: int):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required(request, "/")
        with get_session() as db:
            topic = get_owned_topic(db, topic_id, identity)
            if not topic:
                return Div(notice(t("접근 권한이 없습니다.", "No access."),
                                  kind="error"), id=SCHED_ID)
            entry = entry_for_topic(db, topic.id)
            if entry:
                db.delete(entry)
                db.commit()
            return _sched_interactive(db, topic,
                                      admin_override=is_admin_email(identity))

    @app.get("/board")
    def board(date: str = "", board_lang: str = ""):
        # 전체 페이지는 한 번만 로드 — 이후 board-live 가 스스로 폴링하여 갱신
        _apply_board_language(board_lang)
        with get_session() as db:
            language_interval = board_language_interval(db)
        return layout(t("전광판", "Display Board"), _board_live(date, board_lang),
                      board_language_auto_switch(language_interval), chrome=False)

    @app.get("/board2")
    def board2(board_lang: str = ""):
        """밝은 장소에서 보기 좋은 읽기 전용 테이블형 전광판 시간표."""
        _apply_board_language(board_lang)
        with get_session() as db:
            language_interval = board_language_interval(db)
        return layout(
            t("열린공간 시간표", "OpenSpace Timetable"),
            _board2_live(board_lang),
            board_language_auto_switch(language_interval),
            chrome=False,
            main_cls="content board2-content",
            body_cls="board2",
        )

    @app.get("/board2/live")
    def board2_live(board_lang: str = ""):
        # 전체 페이지를 다시 불러오지 않고 테이블만 주기적으로 갱신한다.
        _apply_board_language(board_lang)
        return _board2_live(board_lang)

    @app.get("/board3")
    def board3(board_lang: str = ""):
        """열린공간 QR 코드만 크게 표시하는 전용 전광판."""
        _apply_board_language(board_lang)
        with get_session() as db:
            language_interval = board_language_interval(db)
        return layout(
            t("열린공간 신청", "OpenSpace Application"),
            _board3_live(board_lang),
            board_language_auto_switch(language_interval),
            chrome=False,
            main_cls="content board3-content",
            body_cls="board3",
        )

    @app.get("/board3/live")
    def board3_live(board_lang: str = ""):
        _apply_board_language(board_lang)
        return _board3_live(board_lang)

    @app.get("/auto-board")
    def auto_board():
        """관리자가 등록한 URL을 순서대로 표시하는 자동 전광판."""
        with get_session() as db:
            urls = auto_board_urls(db)
        if not urls:
            return layout(
                t("자동 전광판", "Auto Board"),
                Div(P(t("관리자에서 자동 전광판 URL을 등록해 주세요.",
                        "Add Auto Board URLs in the admin page.")), cls="auto-board-empty"),
                chrome=False, main_cls="auto-board-content", body_cls="auto-board",
            )
        playlist = json.dumps(
            [{"url": item.url, "duration": item.display_seconds} for item in urls],
            ensure_ascii=False,
        ).replace("</", "<\\/")
        rotate_script = f"""
        (() => {{
          const playlist = {playlist};
          const frame = document.getElementById('auto-board-frame');
          let index = 0;
          const showNext = () => {{
            const item = playlist[index];
            frame.src = item.url;
            index = (index + 1) % playlist.length;
            window.setTimeout(showNext, item.duration * 1000);
          }};
          showNext();
        }})();
        """
        return layout(
            t("자동 전광판", "Auto Board"),
            Div(
                Iframe(id="auto-board-frame", title=t("자동 전광판", "Auto Board"),
                       cls="auto-board-frame"),
                Script(rotate_script),
                cls="auto-board-player",
            ),
            chrome=False, main_cls="auto-board-content", body_cls="auto-board",
        )

    @app.get("/scroll-board")
    def scroll_board():
        """관리자가 지정한 내부 페이지를 전체화면으로 천천히 자동 스크롤한다."""
        with get_session() as db:
            url = scroll_board_url(db)
        if not url:
            return layout(
                t("스크롤 전광판", "Scroll Board"),
                Div(P(t("관리자에서 스크롤할 내부 URL을 등록해 주세요.",
                        "Set an internal URL to scroll in the admin page.")), cls="auto-board-empty"),
                chrome=False, main_cls="scroll-board-content", body_cls="scroll-board",
            )
        scroll_script = """
        (() => {
          const frame = document.getElementById('scroll-board-frame');
          const start = () => {
            const win = frame.contentWindow;
            const doc = frame.contentDocument;
            if (!win || !doc) return;
            const step = () => {
              const root = doc.documentElement;
              const max = Math.max(root.scrollHeight, doc.body ? doc.body.scrollHeight : 0) - win.innerHeight;
              if (win.scrollY >= max - 1) {
                window.setTimeout(() => { win.scrollTo(0, 0); window.setTimeout(step, 800); }, 2000);
                return;
              }
              win.scrollBy(0, 1);
              window.setTimeout(step, 16);
            };
            win.scrollTo(0, 0);
            window.setTimeout(step, 800);
          };
          frame.addEventListener('load', start);
        })();
        """
        return layout(
            t("스크롤 전광판", "Scroll Board"),
            Div(Iframe(src=url, id="scroll-board-frame", title=t("스크롤 전광판", "Scroll Board"),
                       cls="scroll-board-frame"),
                Script(scroll_script), cls="scroll-board-player"),
            chrome=False, main_cls="scroll-board-content", body_cls="scroll-board",
        )

    @app.get("/board/live")
    def board_live(date: str = "", board_lang: str = ""):
        # HTMX 폴링 대상 — board-live div 만 반환해 outerHTML 로 교체(깜빡임 없음)
        _apply_board_language(board_lang)
        return _board_live(date, board_lang)


def _apply_board_language(board_lang: str) -> None:
    """전광판 URL의 언어만 요청 범위에 적용한다. 공용 언어 쿠키는 바꾸지 않는다."""
    if board_lang in {"ko", "en"}:
        set_lang(board_lang)


def _board_live(date: str, board_lang: str = ""):
    """전광판 본문(자가 폴링 컨테이너) — 45초마다 HTMX 로 부드럽게 갱신.

    meta refresh(전체 리로드) 대신 이 div 만 outerHTML 로 교체하므로 깜빡임이 없다.
    날짜(date)는 폴링 URL 에 실어 선택한 날이 유지되게 한다.
    """
    with get_session() as session:
        rooms = {r.id: r for r in all_rooms(session)}
        all_ts = all_timeslots(session)
        slots = schedule_map(session)
        closures = room_slot_closures(session)
        topics = topics_by_id(session)
        events = events_by_timeslot(session)
        qrs = board_qrs(session)

    # 행사 일자 선택 (Pick which day to show on the board).
    day_strs = sorted({t.starts_at.date().isoformat() for t in all_ts})
    selected = date if date in day_strs else (day_strs[0] if day_strs else "")
    timeslots = [t for t in all_ts if t.starts_at.date().isoformat() == selected]

    # 선택한 날의 타임테이블을 한 화면(스크롤 없음)에 카드로 채운다.
    sections = []
    for ts in timeslots:
        # 이벤트(시간만)는 룸 카드들 위에 전체폭 배너 카드로 — 여러 개면 여러 줄.
        ev_banners = [_board_event_card(ev) for ev in events.get(ts.id, [])]
        fully_closed = bool(rooms) and all((room_id, ts.id) in closures for room_id in rooms)
        if fully_closed and not ev_banners:
            continue
        if ts.is_closed:
            # 닫힌 슬롯(키노트·휴식 등)도 카드 한 장으로 표시 — 세션 행과 비슷한 비중
            body = Div(Article(Div(ts.closed_label, cls="title"),
                               cls="board-session board-closed"), cls="board-grid")
            weight = 2.2
        elif fully_closed:
            # 대화 슬롯은 모두 닫혔지만 이벤트 안내는 표시한다.
            body, weight = None, 1.0
        else:
            cards = []
            has_session = False
            for room_id, room in rooms.items():
                entry = slots.get((room_id, ts.id))
                topic = topics.get(entry.topic_id) if entry else None
                if topic and topic.is_active:
                    cards.append(_board_card(room, topic))
                    has_session = True
                elif closure := closures.get((room_id, ts.id)):
                    cards.append(Article(
                        Div(room.name, cls="room"),
                        Div(closure.label or t("닫힘", "Closed"), cls="title"),
                        cls="board-session board-closed"))
                else:
                    cards.append(_board_empty_card(room))  # 빈 칸도 표시
            body = Div(*cards, cls="board-grid")
            # 세션이 있는 행은 높게(제목 다 보이게), 빈 행은 낮게 — 무스크롤 유지
            weight = 2.6 if (has_session or ev_banners) else 1.0
        section_children = [H2(ts.time_label)]
        if ev_banners:
            section_children.append(Div(*ev_banners, cls="board-events"))
        if body is not None:
            section_children.append(body)
        sections.append(Section(*section_children,
                                cls="board-section", style=f"flex:{weight}"))

    # 날짜 탭 (Date tabs) — 여러 날일 때만 노출, ?date= 로 선택 유지
    head_children = [H1(t("전광판", "Display Board"), cls="board-title")]
    if len(day_strs) > 1:
        head_children.append(Div(*[
            A(fmt_day_short(d), href=f"/board?date={d}",
              cls="board-date" + (" is-active" if d == selected else ""))
            for d in day_strs
        ], cls="board-dates"))
    head = Div(*head_children, cls="board-head")

    if sections:
        content = Div(*sections, cls="board-slots")
    else:
        content = P(t("아직 배정된 세션이 없습니다.", "No sessions scheduled yet."),
                    cls="board-empty")
    # QR 은 오른쪽 사이드바로 분리 — 타임테이블 높이에 영향 주지 않음
    body_children = [content]
    qr_side = _board_qr_strip(qrs)
    if qr_side is not None:
        body_children.append(qr_side)
    board_body = Div(*body_children, cls="board-body")

    # 자가 폴링: 45초마다 자신을 outerHTML 로 교체 (전체 페이지 리로드 없음)
    return Div(
        head, board_body,
        id="board-live",
        hx_get=f"/board/live?date={selected}&board_lang={board_lang}",
        hx_trigger="every 45s",
        hx_target="this",
        hx_swap="outerHTML",
    )


def _board2_live(board_lang: str = ""):
    """테이블형 전광판 본문 — 45초마다 일정 데이터만 갱신한다."""
    with get_session() as session:
        rooms = all_rooms(session)
        timeslots = all_timeslots(session)
        slots = schedule_map(session)
        closures = room_slot_closures(session)
        topics = topics_by_id(session)
        events = events_by_timeslot(session)

    if not rooms or not timeslots:
        body = Div(
            Div(H1(t("열린공간 시간표", "OpenSpace Timetable")), cls="board2-title-row"),
            schedule_table(rooms, timeslots, slots, topics, events=events,
                           room_closures=closures),
            cls="board2-day-content",
        )
    else:
        days = sorted({ts.starts_at.date().isoformat() for ts in timeslots})

        def render_day(day: str):
            day_timeslots = [ts for ts in timeslots
                             if ts.starts_at.date().isoformat() == day]
            return Div(
                Div(
                    H1(t("열린공간 시간표", "OpenSpace Timetable")),
                    day_caption(day, suffix=""),
                    cls="board2-title-row",
                ),
                schedule_table(rooms, day_timeslots, slots, topics, events=events,
                               room_closures=closures,
                               show_descriptions=True, show_background_images=True,
                               merge_event_time=True,
                               hide_fully_closed_rows=True,
                               open_label=t("비어있습니다. 열린공간 주제를 넣어주세요!",
                                            "Open — add an OpenSpace topic!")),
                cls="board2-day-content",
            )

        body = date_tabs(days, render_day, id_prefix="b2day", panel_display="flex")

    return Div(
        Div(
            P(
                t("원흥관 3층 ", "Wonheung Hall 3F "),
                Span("i.SPACE-아이닷스페이스", cls="board2-location-name"),
                cls="board2-location",
            ),
            cls="board2-head",
        ),
        Div(body, cls="board2-body"),
        id="board2-live",
        hx_get=f"/board2/live?board_lang={board_lang}",
        hx_trigger="every 45s",
        hx_target="this",
        hx_swap="outerHTML",
    )


def _board3_live(board_lang: str = ""):
    """열린공간 공통 QR만 표시하는 전광판 본문."""
    with get_session() as session:
        qrs = board_qrs(session)
    items = []
    for slot, qr in sorted(qrs.items()):
        if not qr.image_url:
            continue
        caption = qr.caption_en if get_lang() == "en" and qr.caption_en else qr.caption
        items.append(Section(
            H2(caption or t("열린공간 신청", "OpenSpace Application")),
            Img(src=qr.image_url, alt=caption or f"QR {slot}", cls="board3-qr-img"),
            cls="board3-qr-item",
        ))
    return Div(
        H1(t("열린공간 신청", "OpenSpace Application")),
        P(t("QR 코드를 스캔해 열린공간 주제를 등록해 주세요.",
            "Scan the QR code to submit an OpenSpace topic."), cls="board3-lead"),
        Div(*items, cls="board3-qr-grid") if items else notice(
            t("등록된 QR 코드가 없습니다.", "No QR code has been registered.")),
        id="board3-live",
        hx_get=f"/board3/live?board_lang={board_lang}",
        hx_trigger="every 45s",
        hx_target="this",
        hx_swap="outerHTML",
    )


def _board_card(room, topic):
    """전광판 세션 카드 (Board session card).

    이미지는 카드 배경으로 깔고 어두운 그라데이션을 덮어 글자 가독성을 지킨다.
    배경으로 처리하므로 세로 공간을 늘리지 않아 스크롤이 생기지 않는다.
    """
    cls = "board-session"
    attrs = {}
    url = topic.image_url
    # 따옴표·괄호·공백이 없는 안전한 URL만 인라인 배경으로 사용 (CSS 주입 방지)
    if url and not any(ch in url for ch in "'\")\\ \n\t"):
        cls += " has-image"
        attrs["style"] = f"background-image:url('{url}')"
    return Article(
        Div(room.name, cls="room"),
        Div(topic.title, cls="title"),
        cls=cls, **attrs,
    )


def _board_event_card(topic):
    """전광판 이벤트 배너 카드 (Board event banner) — 시간만 등록(룸 없음).

    룸 카드들 위에 전체폭으로 깔아 '이 시간에 진행되는 이벤트'임을 강조한다.
    """
    cls = "board-session board-event"
    attrs = {}
    url = topic.image_url
    if url and not any(ch in url for ch in "'\")\\ \n\t"):
        cls += " has-image"
        attrs["style"] = f"background-image:url('{url}')"
    return Article(
        Div(t("이벤트", "Event"), cls="room board-event-tag"),
        Div(topic.title, cls="title"),
        cls=cls, **attrs,
    )


def _board_empty_card(room):
    """빈 슬롯 카드 (Open/empty slot) — 등록 가능한 자리임을 표시."""
    return Article(
        Div(room.name, cls="room"),
        Div(t("비어있음", "open"), cls="title board-open-title"),
        cls="board-session board-open",
    )


def _board_qr_strip(qrs):
    """전광판 하단 QR 스트립 (Bottom QR strip) — 이미지가 등록된 QR만 표시.

    이미지가 하나도 없으면 None 을 반환해 스트립 자체를 생략한다.
    """
    items = []
    for slot, qr in sorted(qrs.items()):
        if not qr.image_url:
            continue
        children = [Img(src=qr.image_url, alt=f"QR {slot}", cls="board-qr-img")]
        caption = qr.caption_en if get_lang() == "en" and qr.caption_en else qr.caption
        if caption:
            children.append(Div(caption, cls="board-qr-cap"))
        items.append(Div(*children, cls="board-qr-item"))
    if not items:
        return None
    return Div(*items, cls="board-qr")
