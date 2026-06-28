"""공유 UI 컴포넌트 (Shared UI components) — 시맨틱 HTML + 의미있는 CSS 클래스."""
from __future__ import annotations

from datetime import date

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
NAV_ITEMS = [
    ("/topics/new", "주제 등록 (Submit Topic)"),
    ("/topics", "주제 목록 (Topic List)"),
    ("/manage", "내 주제 수정 (Edit My Topic)"),
    ("/schedule", "타임테이블 (Timetable)"),
]

# PyCon 로그인 연동 (Shared PyCon login endpoints) — 주제 등록/수정 게이트 공용.
PYCON_SESSION_URL = (
    "https://rest-api.pycon.kr/authn/social/browser/v1/auth/session"
)
PYCON_SIGNIN_URL = "https://2026.pycon.kr/account/sign-in"


def page_head(title: str, *, auto_refresh: int | None = None):
    """공통 <head> (Common head) — 메타/스타일/HTMX."""
    children = [
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Title(f"{title} · Open Space"),
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
        for path, label in NAV_ITEMS
    ]
    brand = A(
        Span("OS", cls="brand-mark", aria_hidden="true"),
        Span(Span("Open Space", cls="brand-name"),
             Span("언컨퍼런스 (Unconference)", cls="brand-sub"),
             cls="brand-text"),
        href="/", cls="brand", aria_label="Open Space 홈 (Home)",
    )
    return Header(
        brand,
        Nav(*links, aria_label="주요 메뉴 (Main navigation)", cls="main-nav"),
        cls="site-header",
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
        body_children.append(
            Footer(
                P("Open Space MVP — 계정 없이 매직링크로 (No login, magic links only)."),
                cls="site-footer",
            )
        )
    return Html(
        page_head(title, auto_refresh=auto_refresh),
        Body(*body_children, cls="board" if not chrome else "app"),
        lang="ko",
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
                Img(src=topic.image_url, alt=f"{topic.title} 대표 이미지", loading="lazy"),
                cls="topic-figure",
            )
        )
    # 배정 상태 칩 (Scheduled vs unscheduled)
    if scheduled_label:
        status = Span(scheduled_label, cls="topic-status is-scheduled")
    else:
        status = Span("미배정 (Unscheduled)", cls="topic-status is-open")

    children += [
        H3(topic.title, cls="topic-title"),
        P(topic.description or "(설명 없음 / No description)", cls="topic-desc"),
        Footer(
            Span(f"제안자 (Host): {topic.display_host}", cls="topic-host"),
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
        return empty_notice or notice(
            "아직 룸/타임슬롯이 없습니다. 관리자가 먼저 등록해야 합니다. "
            "(No rooms/timeslots yet — admin must add them.)"
        )
    header = Tr(Th("시간 / 룸 (Time / Room)"), *[Th(r.name) for r in rooms])
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
                cells.append(Td(topic.title, cls="slot-filled"))
            else:
                cells.append(Td("— 비어있음 (open)", cls="slot-open"))
        rows.append(Tr(*cells))
    return Table(Thead(header), *rows, cls="schedule")


WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def fmt_day_short(iso: str) -> str:
    """ISO 날짜를 탭 라벨로 (e.g. 2026-09-12 -> 09.12 (토))."""
    d = date.fromisoformat(iso)
    return f"{d:%m.%d} ({WEEKDAYS_KO[d.weekday()]})"


def day_caption(iso: str, suffix: str = " 타임테이블"):
    """표 위에 붙는 날짜 제목 (Full-date caption above a day's table)."""
    d = date.fromisoformat(iso)
    label = f"{d.year}년 {d.month}월 {d.day}일 ({WEEKDAYS_KO[d.weekday()]})"
    return P(Span("📅 ", aria_hidden="true"), Span(label), suffix,
             cls="day-caption")


def date_tabs(days, render_day, *, id_prefix: str, default_day: str | None = None,
              caption_suffix: str = " 타임테이블",
              choose_label: str = "날짜를 선택하세요 (Choose a day):"):
    """순수 CSS 라디오 날짜 탭 (Pure-CSS date tabs, no JS).

    HTMX 패널 스왑·정적 렌더 어디서나 동작한다. 각 날짜 표 위에는 그 날짜를
    제목으로 달아 어떤 날 표인지 분명히 한다.

    days: 정렬된 ISO 날짜 문자열 목록. render_day(day_iso) -> 그 날의 본문.
    id_prefix: 라디오 name/id 접두사 (페이지 내 유일해야 함).
    """
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
            aria_label="날짜 선택 (Choose a day)"),
        Div(*panels, cls="day-panels"),
        cls="daytabs",
    )


__all__ = [
    "layout", "field", "notice", "topic_card", "site_header", "page_head",
    "date_tabs", "day_caption", "fmt_day_short", "WEEKDAYS_KO", "schedule_table",
    "NAV_ITEMS", "PYCON_SESSION_URL", "PYCON_SIGNIN_URL",
    "Div", "P", "H1", "H2", "H3", "A", "Form", "Button", "Ul", "Li", "Span",
]
