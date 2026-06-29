"""공개 페이지 (Public pages): /, /topics, /topics/new, /schedule, /board."""
from __future__ import annotations

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
    Img,
    Input,
    Label,
    P,
    Script,
    Section,
    Small,
    Span,
)
from starlette.datastructures import UploadFile

from ..components import (
    date_tabs,
    field,
    fmt_day_short,
    layout,
    notice,
    pycon_login_gate,
    schedule_table,
    topic_card,
)
from ..database import get_session
from ..mailer import send_magic_link
from ..models import Topic
from ..pycon import verified_email
from ..queries import (
    BOARD_QR_SLOTS,
    active_topics,
    all_rooms,
    all_timeslots,
    board_qrs,
    entry_for_topic,
    schedule_map,
    topics_by_id,
)
from ..security import generate_token, token_expiry
from ..uploads import UploadError, normalize_image_url, save_image


# 입력값을 카드 미리보기에 실시간 반영 (Mirror form inputs into the pinned card)
_LIVE_PREVIEW_JS = """
(function () {
  var map = [
    ['f-title', 'pv-title', '제목을 입력하세요'],
    ['f-description', 'pv-desc', '설명을 입력하세요'],
    ['f-host_name', 'pv-host', '익명 (Anonymous)']
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


def _new_error(message: str):
    """주제 등록 오류 안내 (Submission error page)."""
    return layout(
        "주제 등록 (Submit Topic)",
        notice(message, kind="error"),
        A("돌아가기 (Back)", href="/topics/new", cls="btn secondary"),
        active="/topics/new",
    )


def _image_fields():
    """주제 대표 이미지 입력 (Topic image) — 업로드 또는 URL 둘 다 지원."""
    from fasthtml.common import Fieldset, Legend, Small

    return Fieldset(
        Legend("주제 대표 이미지 (Topic image)"),
        Small("주제를 대표하는 이미지를 업로드하거나 이미지 URL을 입력하세요. (선택) "
              "(Upload an image file or enter an image URL — optional.)",
              cls="field-help"),
        Div(
            Label("파일 업로드 (Upload)", fr="f-image_file"),
            Input(id="f-image_file", name="image_file", type="file",
                  accept="image/png,image/jpeg,image/gif,image/webp"),
            cls="field",
        ),
        Div(
            Label("또는 이미지 URL (or Image URL)", fr="f-image_url"),
            Input(id="f-image_url", name="image_url", type="url", required=False,
                  placeholder="https://example.com/cover.png"),
            cls="field",
        ),
        cls="image-fields",
    )


def register(app) -> None:
    @app.get("/")
    def home():
        return layout(
            "홈 (Home)",
            H1("열린공간 (OpenSpace) — 컨퍼런스 토론 (Conference open space)"),
            P("주제를 제안하고, 매직링크로 직접 타임테이블에 등록하세요. "
              "(Propose a topic and schedule it yourself via a magic link.)"),
            Section(
                A("주제 등록 (Submit Topic)", href="/topics/new", cls="btn"),
                " ",
                A("주제 목록 (Topic List)", href="/topics", cls="btn secondary"),
                " ",
                A("타임테이블 (Timetable)", href="/schedule", cls="btn secondary"),
                " ",
                A("전광판 (Display Board)", href="/board", cls="btn secondary"),
                cls="cta-row",
            ),
        )

    @app.get("/topics")
    def topics_list():
        with get_session() as session:
            topics = active_topics(session)
            slots = schedule_map(session)
            # topic_id -> 슬롯 라벨
            rooms = {r.id: r for r in all_rooms(session)}
            timeslots = {t.id: t for t in all_timeslots(session)}
            scheduled: dict[int, str] = {}
            for (room_id, ts_id), entry in slots.items():
                room = rooms.get(room_id)
                ts = timeslots.get(ts_id)
                if room and ts:
                    scheduled[entry.topic_id] = f"{room.name} · {ts.time_label}"

            cards = [
                topic_card(t, scheduled_label=(
                    f"배정됨 (Scheduled): {scheduled[t.id]}" if t.id in scheduled else None
                ))
                for t in topics
            ]
        body = cards if cards else [notice("아직 제안된 주제가 없습니다. (No topics yet.)")]
        return layout(
            "주제 목록 (Topic List)",
            H1("주제 목록 (Topic List)"),
            A("주제 등록 (Submit Topic)", href="/topics/new", cls="btn"),
            Section(*body, cls="topic-grid"),
        )

    @app.get("/topics/new")
    def topic_new_form(request):
        # 서버가 PyCon 세션을 검증한다 — 미로그인이면 등록 폼을 보여주지 않는다.
        email = verified_email(request)
        if not email:
            return layout(
                "주제 등록 (Submit Topic)",
                H1("주제 등록 (Submit Topic)"),
                pycon_login_gate("/topics/new"),
                active="/topics/new", main_cls="content page-new",
            )
        hero = Header(
            Span("주제 등록 (Submit Topic)", cls="eyebrow"),
            H1(Span("함께 이야기할"), Span("주제를 제안하세요"), cls="hero-title"),
            P("열린공간(OpenSpace)은 참가자가 직접 주제를 제안하고 일정을 정하는 행사입니다. "
              "아래 항목을 입력하면 오른쪽에 미리보기가 표시됩니다. "
              "(OpenSpace lets participants propose topics and set the schedule. "
              "Fill in the fields below and a preview appears on the right.)",
              cls="hero-lede"),
            cls="page-hero",
        )
        form = Form(
            # 이메일은 PyCon 계정에서 서버가 가져온 값 — 읽기 전용으로 보여준다.
            # (POST 시에도 서버가 세션을 재검증하므로 임의 변경은 무시된다.)
            Div(
                Label("이메일 (Email)", fr="f-host_email"),
                Input(id="f-host_email", name="host_email", value=email,
                      type="email", readonly=True),
                Small("PyCon 계정 이메일입니다. (Your PyCon account email.)",
                      cls="field-help"),
                cls="field",
            ),
            field("별명 (Nickname)", "host_name", required=False,
                  placeholder="비워두면 익명으로 표시됩니다 (선택)"),
            field("주제 제목 (Topic Title)", "title",
                  placeholder="예: 파이썬 타입 힌트, 어디까지 써봤나요?"),
            field("설명 (Description)", "description", textarea=True, required=False,
                  placeholder="무엇을 왜 이야기하고 싶은지 한두 문장으로 설명해 주세요."),
            _image_fields(),
            Button("주제 등록 (Submit)", type="submit", cls="btn btn-pin"),
            P("등록하면 관리용 매직링크가 이메일로 전송됩니다. "
              "이 링크로 주제를 수정하거나 일정을 등록할 수 있습니다. "
              "(After you submit, a private magic link is emailed to you "
              "for editing and scheduling.)", cls="form-hint"),
            method="post", action="/topics/new", enctype="multipart/form-data",
            cls="topic-form",
        )
        preview = Aside(
            Div(cls="pin"),
            Article(
                Span("미리보기 (Preview)", cls="card-eyebrow"),
                Div(
                    Img(id="pv-image", alt="주제 대표 이미지 미리보기 (Topic image preview)"),
                    id="pv-figure", cls="card-figure", hidden=True,
                ),
                H2("제목을 입력하세요", id="pv-title", cls="card-title is-empty"),
                P("설명을 입력하세요", id="pv-desc",
                  cls="card-desc is-empty"),
                Footer(
                    Span("제안자 (Host)", cls="card-host-label"),
                    Span("익명 (Anonymous)", id="pv-host", cls="card-host is-empty"),
                    cls="card-foot",
                ),
                cls="pin-card",
            ),
            cls="pin-preview", aria_hidden="true",
        )
        return layout(
            "주제 등록 (Submit Topic)",
            hero,
            Div(Section(form, cls="form-col"), preview,
                cls="new-grid", id="new-grid"),
            Script(_LIVE_PREVIEW_JS),
            active="/topics/new", main_cls="content page-new",
        )

    @app.post("/topics/new")
    async def topic_create(request, title: str, host_name: str = "",
                           description: str = "", image_url: str = "",
                           image_file: UploadFile = None):
        # 이메일은 폼 값(읽기 전용)이 아니라 서버가 검증한 PyCon 세션에서 가져온다.
        host_email = verified_email(request)
        if not host_email:
            return _new_error("PyCon 로그인이 필요합니다. 다시 로그인해 주세요. "
                              "(PyCon login is required — please log in again.)")
        host_name = (host_name or "").strip()
        title = (title or "").strip()
        # 제목만 필수, 별명은 선택 (title required; nickname optional)
        if not title:
            return _new_error("제목은 필수입니다. (Title is required.)")

        # 이미지: 업로드 우선, 없으면 URL (uploaded file wins, else pasted URL)
        try:
            stored = await save_image(image_file)
            final_image = stored or normalize_image_url(image_url)
        except UploadError as exc:
            return _new_error(str(exc))

        raw_token, token_hash = generate_token()
        with get_session() as session:
            topic = Topic(
                title=title,
                description=(description or "").strip(),
                host_name=host_name,
                host_email=host_email,
                image_url=final_image,
                edit_token_hash=token_hash,
                edit_token_expires_at=token_expiry(),
            )
            session.add(topic)
            session.commit()
            session.refresh(topic)
            send_magic_link(host_email, raw_token, topic.title)

        return layout(
            "등록 완료 (Submitted)",
            H1("주제가 등록되었습니다! (Topic submitted!)"),
            notice("관리용 매직링크를 이메일로 보냈습니다. 메일함을 확인하세요. "
                   "(Check your email for the private manage link.)", kind="success"),
            P("개발 모드에서는 서버 콘솔에 링크가 출력됩니다. "
              "(In dev mode the link is printed to the server console.)"),
            A("주제 목록 보기 (View topics)", href="/topics", cls="btn secondary"),
        )

    @app.get("/schedule")
    def schedule():
        with get_session() as session:
            rooms = all_rooms(session)
            timeslots = all_timeslots(session)
            slots = schedule_map(session)
            topics = topics_by_id(session)
        if not rooms or not timeslots:
            body = schedule_table(rooms, timeslots, slots, topics)  # 안내 노출
        else:
            # 여러 날이면 날짜 탭으로 나눠 보여준다 (split by day with date tabs).
            days = sorted({t.starts_at.date().isoformat() for t in timeslots})

            def render_day(day: str):
                day_ts = [t for t in timeslots
                          if t.starts_at.date().isoformat() == day]
                return schedule_table(rooms, day_ts, slots, topics)

            body = date_tabs(days, render_day, id_prefix="sday")
        return layout(
            "타임테이블 (Timetable)",
            H1("타임테이블 (Timetable)"),
            body,
        )

    @app.get("/board")
    def board(date: str = ""):
        # 전체 페이지는 한 번만 로드 — 이후 board-live 가 스스로 폴링하여 갱신
        return layout("전광판 (Display Board)", _board_live(date), chrome=False)

    @app.get("/board/live")
    def board_live(date: str = ""):
        # HTMX 폴링 대상 — board-live div 만 반환해 outerHTML 로 교체(깜빡임 없음)
        return _board_live(date)


def _board_live(date: str):
    """전광판 본문(자가 폴링 컨테이너) — 45초마다 HTMX 로 부드럽게 갱신.

    meta refresh(전체 리로드) 대신 이 div 만 outerHTML 로 교체하므로 깜빡임이 없다.
    날짜(date)는 폴링 URL 에 실어 선택한 날이 유지되게 한다.
    """
    with get_session() as session:
        rooms = {r.id: r for r in all_rooms(session)}
        all_ts = all_timeslots(session)
        slots = schedule_map(session)
        topics = topics_by_id(session)
        qrs = board_qrs(session)

    # 행사 일자 선택 (Pick which day to show on the board).
    day_strs = sorted({t.starts_at.date().isoformat() for t in all_ts})
    selected = date if date in day_strs else (day_strs[0] if day_strs else "")
    timeslots = [t for t in all_ts if t.starts_at.date().isoformat() == selected]

    # 선택한 날의 타임테이블을 한 화면(스크롤 없음)에 카드로 채운다.
    sections = []
    for ts in timeslots:
        if ts.is_closed:
            # 닫힌 슬롯(키노트·휴식 등)도 카드 한 장으로 표시 — 세션 행과 비슷한 비중
            body = Div(Article(Div(ts.closed_label, cls="title"),
                               cls="board-session board-closed"), cls="board-grid")
            weight = 2.2
        else:
            cards = []
            has_session = False
            for room_id, room in rooms.items():
                entry = slots.get((room_id, ts.id))
                topic = topics.get(entry.topic_id) if entry else None
                if topic and topic.is_active:
                    cards.append(_board_card(room, topic))
                    has_session = True
                else:
                    cards.append(_board_empty_card(room))  # 빈 칸도 표시
            body = Div(*cards, cls="board-grid")
            # 세션이 있는 행은 높게(제목 다 보이게), 빈 행은 낮게 — 무스크롤 유지
            weight = 2.6 if has_session else 1.0
        sections.append(Section(H2(ts.time_label), body,
                                cls="board-section", style=f"flex:{weight}"))

    # 날짜 탭 (Date tabs) — 여러 날일 때만 노출, ?date= 로 선택 유지
    head_children = [H1("전광판 (Display Board)", cls="board-title")]
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
        content = P("아직 배정된 세션이 없습니다. (No sessions scheduled yet.)",
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
        hx_get=f"/board/live?date={selected}",
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


def _board_empty_card(room):
    """빈 슬롯 카드 (Open/empty slot) — 등록 가능한 자리임을 표시."""
    return Article(
        Div(room.name, cls="room"),
        Div("비어있음 (open)", cls="title board-open-title"),
        cls="board-session board-open",
    )


def _board_qr_strip(qrs):
    """전광판 하단 QR 스트립 (Bottom QR strip) — 이미지가 등록된 QR만 표시.

    이미지가 하나도 없으면 None 을 반환해 스트립 자체를 생략한다.
    """
    items = []
    for slot in BOARD_QR_SLOTS:
        qr = qrs.get(slot)
        if not qr or not qr.image_url:
            continue
        children = [Img(src=qr.image_url, alt=f"QR {slot}", cls="board-qr-img")]
        if qr.caption:
            children.append(Div(qr.caption, cls="board-qr-cap"))
        items.append(Div(*children, cls="board-qr-item"))
    if not items:
        return None
    return Div(*items, cls="board-qr")
