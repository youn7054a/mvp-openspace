"""공유 UI 컴포넌트 (Shared UI components) — 시맨틱 HTML + 의미있는 CSS 클래스."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

from .i18n import get_lang, get_path, t

from fasthtml.common import (
    A,
    Body,
    Button,
    Div,
    Footer,
    Form,
    H1,
    H2,
    H3,
    Head,
    Header,
    Html,
    Input,
    Label,
    Li,
    Link,
    Main,
    Meta,
    Nav,
    NotStr,
    P,
    Script,
    Span,
    Style,
    Table,
    Td,
    Th,
    Thead,
    Title,
    Tr,
    Ul,
)

# 공개 내비게이션 항목 (Public nav items): (경로, 라벨)
# 참가자 흐름만 노출 — 홈은 로고로, 전광판(/board)은 URL로만 접근.
# 라벨은 요청 언어에 따라 달라지므로 함수로 생성 (built per-request for i18n).
def nav_items():
    from .auth import current_identity, is_admin_email

    items = [
        ("/", t("주제 등록", "Submit Topic")),
        ("/topics", t("주제 목록", "Topic List")),
        ("/schedule", t("타임테이블", "Timetable")),
        ("/my", t("내 주제", "MY")),
    ]
    # 관리자 이메일로 로그인했으면 관리자 탭 노출 (admin tab for admin identities).
    if is_admin_email(current_identity()):
        items.append(("/admin", t("관리자", "Admin")))
    return items


def account_field(email: str):
    """수정 불가 '등록 계정' 필드 — 입력칸과 같은 형식(읽기 전용)."""
    return Div(
        Label(t("등록 계정 (Account)", "Account")),
        Input(value=email, readonly=True, tabindex="-1", cls="is-readonly",
              aria_label=t("등록 계정 (수정 불가)", "Account (read-only)")),
        cls="field field-readonly",
    )


def topic_text_fields(topic=None):
    """등록·수정 공용 텍스트 필드 (별명/제목/설명) — 같은 폼을 공유.

    topic 이 주어지면 수정 모드로 값이 채워진다. 이메일·pycon_id 는 신원에서
    공급하므로 폼에 두지 않는다.
    """
    name = topic.host_name if topic else ""
    title = topic.title if topic else ""
    desc = topic.description if topic else ""
    return [
        field(t("별명", "Nickname"), "host_name", value=name, required=False,
              placeholder=t("비워두면 익명으로 표시됩니다 (선택)",
                            "Leave blank to appear as Anonymous (optional)")),
        field(t("주제 제목", "Topic Title"), "title", value=title,
              placeholder=t("예: 파이썬 타입 힌트, 어디까지 써봤나요?",
                            "e.g. Python type hints — how far do you go?")),
        field(t("설명", "Description"), "description", value=desc,
              textarea=True, required=False,
              placeholder=t("무엇을 왜 이야기하고 싶은지 한두 문장으로 설명해 주세요.",
                            "Describe what you want to discuss and why, in a sentence or two.")),
    ]

# PyCon Korea 공식 푸터 재현 (replicated from 2026.pycon.kr) — 소셜 아이콘 path.
_FOOT_SOCIALS = [
    ("mailto:pyconkr@pycon.kr", "이메일 보내기", False,
     "M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2"
     "m0 4-8 5-8-5V6l8 5 8-5z"),
    ("https://www.facebook.com/pyconkorea/", "Facebook", True,
     "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2m13 2h-2.5A3.5 "
     "3.5 0 0 0 12 8.5V11h-2v3h2v7h3v-7h3v-3h-3V9a1 1 0 0 1 1-1h2V5z"),
    ("https://www.youtube.com/c/PyConKRtube", "YouTube", True,
     "M10 15l5.19-3L10 9v6m11.56-7.83c.13.47.22 1.1.28 1.9.07.8.1 1.49.1 2.09L22 12c0 2.19-"
     ".16 3.8-.44 4.83-.25.9-.83 1.48-1.73 1.73-.47.13-1.33.22-2.65.28-1.3.07-2.49.1-3.59.1"
     "L12 19c-4.19 0-6.8-.16-7.83-.44-.9-.25-1.48-.83-1.73-1.73-.13-.47-.22-1.1-.28-1.9-.07"
     "-.8-.1-1.49-.1-2.09L2 12c0-2.19.16-3.8.44-4.83.25-.9.83-1.48 1.73-1.73.47-.13 1.33-"
     ".22 2.65-.28 1.3-.07 2.49-.1 3.59-.1L12 5c4.19 0 6.8.16 7.83.44.9.25 1.48.83 1.73 "
     "1.73z"),
    ("https://x.com/PyConKR", "X", True,
     "M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-"
     "8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"),
    ("https://github.com/pythonkr", "GitHub", True,
     "M12 1.27a11 11 0 00-3.48 21.46c.55.09.73-.28.73-.55v-1.84c-3.03.64-3.67-1.46-3.67-"
     "1.46-.55-1.29-1.28-1.65-1.28-1.65-.92-.65.1-.65.1-.65 1.1 0 1.73 1.1 1.73 1.1.92 "
     "1.65 2.57 1.2 3.21.92a2 2 0 01.64-1.47c-2.47-.27-5.04-1.19-5.04-5.5 0-1.1.46-2.1 "
     "1.2-2.84a3.76 3.76 0 010-2.93s.91-.28 3.11 1.1c1.8-.49 3.7-.49 5.5 0 2.1-1.38 3.02-"
     "1.1 3.02-1.1a3.76 3.76 0 010 2.93c.83.74 1.2 1.74 1.2 2.94 0 4.21-2.57 5.13-5.04 "
     "5.4.45.37.82.92.82 2.02v3.03c0 .27.1.64.73.55A11 11 0 0012 1.27"),
    ("https://www.instagram.com/pycon_korea/", "Instagram", True,
     "M7.8 2h8.4C19.4 2 22 4.6 22 7.8v8.4a5.8 5.8 0 0 1-5.8 5.8H7.8C4.6 22 2 19.4 2 16.2V7.8"
     "A5.8 5.8 0 0 1 7.8 2m-.2 2A3.6 3.6 0 0 0 4 7.6v8.8C4 18.39 5.61 20 7.6 20h8.8a3.6 3.6 "
     "0 0 0 3.6-3.6V7.6C20 5.61 18.39 4 16.4 4H7.6m9.65 1.5a1.25 1.25 0 0 1 1.25 1.25A1.25 "
     "1.25 0 0 1 17.25 8 1.25 1.25 0 0 1 16 6.75a1.25 1.25 0 0 1 1.25-1.25M12 7a5 5 0 0 1 5 "
     "5 5 5 0 0 1-5 5 5 5 0 0 1-5-5 5 5 0 0 1 5-5m0 2a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 "
     "3-3 3 3 0 0 0-3-3z"),
    ("https://www.linkedin.com/company/pyconkorea/", "LinkedIn", True,
     "M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a"
     "3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.32 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77"
     ".62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.79M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c"
     "0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v"
     "-8.37H5.5v8.37h2.77z"),
    ("https://blog.pycon.kr/", "Blog", True,
     "M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2m-5 14H7v"
     "-2h7zm3-4H7v-2h10zm0-4H7V7h10z"),
]


def site_footer():
    """가벼운 푸터 (PyCon 스타일) — 행동강령·정책 링크 + 소셜 + 저작권.

    OpenSpace 는 상거래 사이트가 아니므로 법인/사업자/판매 정보는 싣지 않는다.
    """
    sep = Span(" · ", cls="foot-sep")
    policies = P(
        A("PyCon Korea Code of Conduct",
          href="https://pythonkr.github.io/pycon-code-of-conduct/ko/coc/"
               "a_intent_and_purpose.html", target="_blank", rel="noreferrer",
          cls="foot-link"),
        sep,
        A("Privacy Policy", href="https://2026.pycon.kr/about/privacy-policy",
          target="_blank", rel="noreferrer", cls="foot-link"),
        cls="foot-policies",
    )
    icons = []
    for href, label, blank, path_d in _FOOT_SOCIALS:
        svg = NotStr(
            '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" '
            f'aria-hidden="true"><path d="{path_d}"></path></svg>')
        attrs = {"target": "_blank", "rel": "noopener noreferrer"} if blank else {}
        icons.append(A(svg, href=href, aria_label=label, cls="foot-social", **attrs))
    # Flickr (viewBox 다름) 추가
    flickr = NotStr(
        '<svg viewBox="0 0 17 10" width="18" height="18" fill="currentColor" '
        'aria-hidden="true"><path d="M11.94.56c-.71 0-1.4.17-2.03.49-.62.32-1.16.79-1.57 '
        '1.37-.41-.58-.95-1.05-1.58-1.37A4.4 4.4 0 0 0 4.73.56 4.44 4.44 0 0 0 .29 5c0 '
        '2.45 1.99 4.44 4.44 4.44 1.49 0 2.8-.73 3.6-1.86a4.43 4.43 0 0 0 3.61 1.86A4.44 '
        '4.44 0 0 0 16.38 5 4.44 4.44 0 0 0 11.94.56m0 8.08A3.64 3.64 0 0 1 8.3 5a3.64 '
        '3.64 0 0 1 3.64-3.64A3.64 3.64 0 0 1 15.58 5a3.64 3.64 0 0 1-3.64 3.64"></path>'
        '</svg>')
    icons.append(A(flickr, href="https://www.flickr.com/photos/126829363@N08/",
                   aria_label="Flickr", target="_blank", rel="noopener noreferrer",
                   cls="foot-social"))
    socials = Div(*icons, cls="foot-socials")
    copy = Div("© 2026, Python Korea, All rights reserved.", cls="foot-copy")
    return Footer(socials, policies, copy, cls="site-footer")


def page_head(title: str, *, auto_refresh: int | None = None):
    """공통 <head> (Common head) — 메타/스타일/HTMX."""
    children = [
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Title(f"{title} · {t('열린공간', 'OpenSpace')}"),
        Script(src="https://unpkg.com/htmx.org@1.9.12"),
        # 폰트 (Fonts): 레트로 네온 — Press Start 2P(영문 픽셀) + Galmuri(한글 픽셀)
        Link(rel="preconnect", href="https://fonts.googleapis.com"),
        Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        Link(rel="stylesheet", href=(
            "https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap"
        )),
        Link(rel="stylesheet",
             href="https://cdn.jsdelivr.net/npm/galmuri/dist/galmuri.css"),
        Link(rel="stylesheet", href="/static/app.css"),
    ]
    if auto_refresh:
        # 전광판 자동 새로고침 (Display board auto refresh)
        children.append(Meta(http_equiv="refresh", content=str(auto_refresh)))
    return Head(*children)


def site_header(active: str | None = None):
    """헤더 + 내비게이션 (Header & navigation).

    active: 현재 경로를 넘기면 해당 nav 항목을 강조 (current page highlight).
    """
    links = [
        A(label, href=path,
          cls="nav-link" + (" is-active" if path == active else ""),
          **({"aria_current": "page"} if path == active else {}))
        for path, label in nav_items()
    ]
    brand = A(
        Span("OS", cls="brand-mark", aria_hidden="true"),
        Span(Span("열린공간", cls="brand-name"),
             Span("OpenSpace", cls="brand-sub"),
             cls="brand-text"),
        href="/", cls="brand",
        aria_label=t("열린공간 홈", "OpenSpace Home"),
    )
    return Header(
        brand,
        Nav(*links, aria_label=t("주요 메뉴", "Main navigation"), cls="main-nav"),
        lang_toggle(),
        cls="site-header",
    )


def lang_toggle():
    """헤더 언어 토글 (Header language switch) — KO | EN, 현재 언어 강조."""
    nxt = quote(get_path(), safe="")
    cur = get_lang()
    return Nav(
        A("KO", href=f"/lang/ko?next={nxt}",
          cls="lang-link" + (" is-active" if cur == "ko" else ""),
          **({"aria_current": "true"} if cur == "ko" else {})),
        Span("|", cls="lang-sep", aria_hidden="true"),
        A("EN", href=f"/lang/en?next={nxt}",
          cls="lang-link" + (" is-active" if cur == "en" else ""),
          **({"aria_current": "true"} if cur == "en" else {})),
        cls="lang-toggle", aria_label=t("언어 선택", "Language"),
    )


def layout(title: str, *content, auto_refresh: int | None = None,
           chrome: bool = True, active: str | None = None, main_cls: str = "content"):
    """표준 페이지 레이아웃 (Standard page layout).

    chrome=False 면 헤더/푸터 없는 전광판용 풀스크린 레이아웃.
    active: 현재 경로 (nav 강조). main_cls: <main> 추가 클래스 (페이지별 레이아웃).
    """
    body_children = []
    if chrome:
        body_children.append(site_header(active=active))
    body_children.append(Main(*content, cls=main_cls))
    if chrome:
        body_children.append(site_footer())
    return Html(
        page_head(title, auto_refresh=auto_refresh),
        Body(*body_children, cls="board" if not chrome else "app"),
        lang=get_lang(),
    )


def field(label_text: str, name: str, *, value: str = "", input_type: str = "text",
          required: bool = True, textarea: bool = False, placeholder: str = ""):
    """라벨이 붙은 폼 필드 (Labeled form field) — 접근성 위해 label 필수."""
    from fasthtml.common import Textarea

    field_id = f"f-{name}"
    if textarea:
        control = Textarea(
            value, id=field_id, name=name, required=required,
            placeholder=placeholder, rows=5,
        )
    else:
        control = Input(
            id=field_id, name=name, value=value, type=input_type,
            required=required, placeholder=placeholder,
        )
    return Div(Label(label_text, fr=field_id), control, cls="field")


def notice(message: str, *, kind: str = "info"):
    """안내 배너 (Notice banner). kind: info|success|error."""
    return Div(P(message), cls=f"notice notice-{kind}", role="status")


def topic_card(topic, *, scheduled_label: str | None = None):
    """공개 주제 카드 (Public topic card) — 벽에 핀으로 꽂힌 스티커 모양.

    이메일은 노출하지 않으며, 타임테이블 배정 여부를 칩으로 표시한다.
    """
    from fasthtml.common import Article, Img

    children = []
    if topic.image_url:
        children.append(
            Div(
                Img(src=topic.image_url,
                    alt=f"{topic.title} {t('대표 이미지', 'cover image')}",
                    loading="lazy"),
                cls="topic-figure",
            )
        )
    # 배정 상태 칩 (Scheduled vs unscheduled)
    if scheduled_label:
        status = Span(scheduled_label, cls="topic-status is-scheduled")
    else:
        status = Span(t("미배정", "Unscheduled"), cls="topic-status is-open")

    children += [
        H3(topic.title, cls="topic-title"),
        P(topic.description or t("(설명 없음)", "(No description)"), cls="topic-desc"),
        Footer(
            Span(f"{t('제안자', 'Host')}: {topic.display_host}", cls="topic-host"),
            status,
            cls="topic-foot",
        ),
    ]
    return Article(*children, cls="topic-card sticker")


def schedule_table(rooms, timeslots, slots, topics, *, empty_notice=None):
    """룸×타임슬롯 격자 표 (Room×timeslot grid table).

    slots: (room_id, timeslot_id) -> ScheduleEntry. topics: id -> Topic.
    닫힌 슬롯은 라벨을 전체 열에 표시, 빈 칸은 '비어있음', 배정된 칸은 제목.
    """
    if not rooms or not timeslots:
        return empty_notice or notice(t(
            "아직 룸/타임슬롯이 없습니다. 관리자가 먼저 등록해야 합니다.",
            "No rooms/timeslots yet — admin must add them.",
        ))
    header = Tr(Th(t("시간 / 룸", "Time / Room")), *[Th(r.name) for r in rooms])
    rows = []
    for ts in timeslots:
        if ts.is_closed:
            rows.append(Tr(
                Th(ts.time_label, scope="row"),
                Td(ts.closed_label, colspan=len(rooms), cls="slot-closed"),
            ))
            continue
        cells = [Th(ts.time_label, scope="row")]
        for room in rooms:
            entry = slots.get((room.id, ts.id))
            topic = topics.get(entry.topic_id) if entry else None
            if topic and topic.is_active:
                cells.append(Td(topic.title, cls="slot-filled", title=topic.title))
            else:
                cells.append(Td(t("— 비어있음", "— open"), cls="slot-open"))
        rows.append(Tr(*cells))
    # 좁은 화면에서 가로 스크롤 (mobile: scroll wide tables instead of overflow).
    return Div(Table(Thead(header), *rows, cls="schedule"), cls="schedule-scroll")


WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
WEEKDAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]


def _weekday(d: date) -> str:
    """요일 라벨 (Localized weekday) — 토 / Sat."""
    return (WEEKDAYS_EN if get_lang() == "en" else WEEKDAYS_KO)[d.weekday()]


def fmt_day_short(iso: str) -> str:
    """ISO 날짜를 탭 라벨로 (e.g. 09.12 (토) / Sep 12 (Sat))."""
    d = date.fromisoformat(iso)
    if get_lang() == "en":
        return f"{MONTHS_EN[d.month - 1][:3]} {d.day} ({_weekday(d)})"
    return f"{d:%m.%d} ({_weekday(d)})"


def day_caption(iso: str, suffix: str | None = None):
    """표 위에 붙는 날짜 제목 (Full-date caption above a day's table)."""
    if suffix is None:
        suffix = t(" 타임테이블", " timetable")
    d = date.fromisoformat(iso)
    if get_lang() == "en":
        label = f"{MONTHS_EN[d.month - 1]} {d.day}, {d.year} ({_weekday(d)})"
    else:
        label = f"{d.year}년 {d.month}월 {d.day}일 ({_weekday(d)})"
    return P(Span("📅 ", aria_hidden="true"), Span(label), suffix,
             cls="day-caption")


def date_tabs(days, render_day, *, id_prefix: str, default_day: str | None = None,
              caption_suffix: str | None = None,
              choose_label: str | None = None):
    """순수 CSS 라디오 날짜 탭 (Pure-CSS date tabs, no JS).

    HTMX 패널 스왑·정적 렌더 어디서나 동작한다. 각 날짜 표 위에는 그 날짜를
    제목으로 달아 어떤 날 표인지 분명히 한다.

    days: 정렬된 ISO 날짜 문자열 목록. render_day(day_iso) -> 그 날의 본문.
    id_prefix: 라디오 name/id 접두사 (페이지 내 유일해야 함).
    """
    if choose_label is None:
        choose_label = t("날짜를 선택하세요:", "Choose a day:")
    days = list(days)
    if not days:
        return None
    if len(days) == 1:
        return Div(day_caption(days[0], caption_suffix), render_day(days[0]),
                   cls="daytabs-single")
    if default_day not in days:
        default_day = days[0]

    radios, tabs, panels, rules = [], [], [], []
    for i, day in enumerate(days):
        rid = f"{id_prefix}-{i}"
        radios.append(Input(type="radio", name=id_prefix, id=rid,
                            cls="day-radio", checked=(day == default_day)))
        tabs.append(Label(fmt_day_short(day), fr=rid, cls="day-tab"))
        panels.append(Div(
            day_caption(day, caption_suffix), render_day(day),
            cls="day-panel", **{"data-i": str(i)},
        ))
        # 선택된 라디오에 해당하는 패널만 표시 (show only the checked day's panel).
        rules.append(
            f"#{rid}:checked ~ .day-panels .day-panel[data-i='{i}']{{display:block}}"
        )
    return Div(
        *radios,
        Style(" ".join(rules)),
        P(choose_label, cls="daytabs-label"),
        Div(*tabs, cls="date-tabs", role="tablist",
            aria_label=t("날짜 선택", "Choose a day")),
        Div(*panels, cls="day-panels"),
        cls="daytabs",
    )


__all__ = [
    "layout", "field", "notice", "topic_card", "site_header", "page_head",
    "lang_toggle", "date_tabs", "day_caption", "fmt_day_short", "WEEKDAYS_KO",
    "schedule_table", "nav_items", "topic_text_fields", "account_field",
    "Div", "P", "H1", "H2", "H3", "A", "Form", "Button", "Ul", "Li", "Span",
]
