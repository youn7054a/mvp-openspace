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
    Span,
)
from starlette.datastructures import UploadFile

from ..components import (
    PYCON_SESSION_URL,
    PYCON_SIGNIN_URL,
    date_tabs,
    field,
    fmt_day_short,
    layout,
    notice,
    schedule_table,
    topic_card,
)
from ..database import get_session
from ..mailer import send_magic_link
from ..models import Topic
from ..queries import (
    active_topics,
    all_rooms,
    all_timeslots,
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
    ['f-description', 'pv-desc', '어떤 이야기를 나누고 싶나요?'],
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


# PyCon 로그인으로 주제 등록을 보호한다 (Gate topic submission behind PyCon login).
# - allauth headless 세션 엔드포인트: 인증 시 data.user.email 제공.
# - 쿠키가 필요하므로 브라우저에서 credentials:'include' 로 호출한다.
# - 미로그인(확정) 시 PyCon 로그인 페이지로 보낸다.
# - PyCon 장애/네트워크 오류 시에는 막지 않고 수동 입력 폼을 노출한다(폴백).
_PYCON_GATE_JS = """
(function () {
  var EP = '%s';
  var SIGNIN = '%s';
  var input = document.getElementById('f-host_email');
  var status = document.getElementById('pycon-status');
  var gate = document.getElementById('pycon-gate');
  var grid = document.getElementById('new-grid');
  var done = false;
  function reveal() {
    if (gate) gate.hidden = true;
    if (grid) grid.hidden = false;
  }
  // 외부 응답이 늦어도 폼이 영영 안 뜨는 일이 없게 안전망 (reveal fallback).
  var timer = setTimeout(function () {
    if (done) return; done = true; reveal();
  }, 5000);
  fetch(EP, { credentials: 'include', headers: { 'Accept': 'application/json' } })
    .then(function (res) { return res.json(); })
    .then(function (body) {
      if (done) return; done = true; clearTimeout(timer);
      var authed = body && body.meta && body.meta.is_authenticated;
      if (!authed) { window.location.replace(SIGNIN); return; }  // 로그인 요구
      var user = body.data && body.data.user;
      var email = user && user.email;
      if (email && input && !input.value.trim()) input.value = email;
      if (email && status) {
        status.textContent =
          'PyCon 계정 이메일을 불러왔어요 (' + email + '). (Filled from your PyCon login.)';
        status.hidden = false;
      }
      reveal();
    })
    .catch(function () {
      // 비로그인이 아니라 장애/네트워크 오류 — 막지 않고 수동 입력 허용.
      if (done) return; done = true; clearTimeout(timer); reveal();
    });
})();
""" % (PYCON_SESSION_URL, PYCON_SIGNIN_URL)


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
        Small("주제를 한눈에 보여줄 이미지를 올리거나 링크를 붙여넣으세요. (선택) "
              "(Upload a file or paste an image link — optional.)",
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
            H1("Open Space — 컨퍼런스 토론 (Conference Open Space)"),
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
    def topic_new_form():
        hero = Header(
            Span("주제 등록 (Submit Topic)", cls="eyebrow"),
            H1(Span("열고 싶은 대화를"), Span("벽에 붙여주세요"), cls="hero-title"),
            P("오픈 스페이스는 참가자가 직접 주제를 제안하고 일정을 잡는 자리예요. "
              "카드를 채우면 오른쪽 미리보기가 함께 완성됩니다. "
              "(Fill the card — the pinned preview fills in as you type.)",
              cls="hero-lede"),
            cls="page-hero",
        )
        form = Form(
            field("이메일 (Email)", "host_email", input_type="email",
                  placeholder="you@example.com"),
            P(id="pycon-status", cls="field-help pycon-status", hidden=True),
            field("별명 (Nickname)", "host_name", required=False,
                  placeholder="비워두면 익명으로 표시돼요 (optional)"),
            field("주제 제목 (Topic Title)", "title",
                  placeholder="예: 파이썬 타입 힌트, 어디까지 써봤나요?"),
            field("설명 (Description)", "description", textarea=True, required=False,
                  placeholder="무엇을, 왜 이야기하고 싶은지 한두 문장으로 적어주세요."),
            _image_fields(),
            Button("카드 붙이기 (Pin my topic)", type="submit", cls="btn btn-pin"),
            P("제출하면 관리용 매직링크가 이메일로 전송됩니다. "
              "이 링크로 주제를 수정하거나 일정을 잡을 수 있어요. "
              "(A private magic link will be emailed to you.)", cls="form-hint"),
            method="post", action="/topics/new", enctype="multipart/form-data",
            cls="topic-form",
        )
        preview = Aside(
            Div(cls="pin"),
            Article(
                Span("제안 주제 (Topic)", cls="card-eyebrow"),
                Div(
                    Img(id="pv-image", alt="주제 대표 이미지 미리보기 (Topic image preview)"),
                    id="pv-figure", cls="card-figure", hidden=True,
                ),
                H2("제목을 입력하세요", id="pv-title", cls="card-title is-empty"),
                P("어떤 이야기를 나누고 싶나요?", id="pv-desc",
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
        gate = Div(
            P("PyCon 로그인 확인 중… (Checking your PyCon login…)"),
            id="pycon-gate", cls="notice notice-info", role="status",
        )
        return layout(
            "주제 등록 (Submit Topic)",
            hero,
            gate,
            Div(Section(form, cls="form-col"), preview,
                cls="new-grid", id="new-grid", hidden=True),
            Script(_LIVE_PREVIEW_JS),
            Script(_PYCON_GATE_JS),
            active="/topics/new", main_cls="content page-new",
        )

    @app.post("/topics/new")
    async def topic_create(host_email: str, title: str, host_name: str = "",
                           description: str = "", image_url: str = "",
                           image_file: UploadFile = None):
        host_name = (host_name or "").strip()
        host_email = (host_email or "").strip()
        title = (title or "").strip()
        # 이메일·제목만 필수, 별명은 선택 (email + title required; nickname optional)
        if not (host_email and title):
            return _new_error("이메일과 제목은 필수입니다. (Email and title are required.)")

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
        with get_session() as session:
            rooms = {r.id: r for r in all_rooms(session)}
            all_ts = all_timeslots(session)
            slots = schedule_map(session)
            topics = topics_by_id(session)

        # 행사 일자 선택 (Pick which day to show on the board).
        day_strs = sorted({t.starts_at.date().isoformat() for t in all_ts})
        selected = date if date in day_strs else (day_strs[0] if day_strs else "")
        timeslots = [t for t in all_ts if t.starts_at.date().isoformat() == selected]

        # 선택한 날의 타임테이블을 한 화면(스크롤 없음)에 카드로 채운다.
        # 빈 슬롯도 모두 보여줘서(비어있음) 어떤 시간이 열려있는지 알 수 있게 한다.
        sections = []
        for ts in timeslots:
            if ts.is_closed:
                # 닫힌 슬롯(키노트·휴식 등)도 카드 한 장으로 표시
                body = Div(Article(Div(ts.closed_label, cls="title"),
                                   cls="board-session board-closed"), cls="board-grid")
                weight = 1.4
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

        # 날짜 탭 (Date tabs) — 여러 날일 때만 노출, ?date= 로 자동 새로고침에도 유지
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
        return layout("전광판 (Display Board)", head, content,
                      auto_refresh=45, chrome=False)


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
