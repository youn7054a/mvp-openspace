"""공유 UI 컴포넌트 (Shared UI components) — 시맨틱 HTML + 의미있는 CSS 클래스."""
from __future__ import annotations

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
    Title,
    Ul,
)

# 공개 내비게이션 항목 (Public nav items): (경로, 라벨)
NAV_ITEMS = [
    ("/", "홈 (Home)"),
    ("/topics", "주제 목록 (Topic List)"),
    ("/topics/new", "주제 등록 (Submit Topic)"),
    ("/schedule", "타임테이블 (Timetable)"),
    ("/board", "전광판 (Display Board)"),
]


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


__all__ = [
    "layout", "field", "notice", "topic_card", "site_header", "page_head",
    "Div", "P", "H1", "H2", "H3", "A", "Form", "Button", "Ul", "Li", "Span",
]
