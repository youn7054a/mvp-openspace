"""라이트닝토크: 신청(/light), 관리자(/admin/light), 안내 전광판(/light/board)."""
from __future__ import annotations

from datetime import date, datetime
from hmac import compare_digest
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fasthtml.common import A, Button, Div, Form, H1, H2, Img, Input, P, RedirectResponse, Section, Table, Td, Th, Thead, Tr
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from starlette.datastructures import UploadFile

from ..auth import identity_from_session, login_required_page, note_identity, resolve_identity
from ..components import board_language_auto_switch, field, layout, notice
from ..config import get_settings
from ..database import get_session
from ..i18n import get_lang, set_lang, t
from ..models import LightningApplication, LightningQR, LightningSession, LightningSetting, LightningStatus, utcnow
from ..queries import (board_language_interval, lightning_application_notice,
                       lightning_application_notice_en, lightning_qrs, lightning_sessions)
from ..uploads import UploadError, delete_local_image, normalize_image_url, save_image


def _admin_layout(title, *content):
    # admin 모듈 초기화 후에만 가져와 순환 import를 피한다.
    from .admin import _admin_layout as base_layout
    return base_layout(title, *content)


def _require_admin(session):
    # 현장 운영자는 라이트닝 관리 경로에만 비밀번호로 접근할 수 있다.
    if session.get("light_operator_authenticated"):
        return None
    from .admin import _require_admin as base_require_admin
    return base_require_admin(session)


def _valid_material_url(value: str) -> str | None:
    """현장에서 바로 열 수 있는 http/https 공유 URL만 받는다."""
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _today() -> date:
    """신청 가능 날짜 판정용 — 행사 현장 시간(Asia/Seoul)을 기준으로 한다."""
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _time_label(value: str) -> str:
    """HH:MM 저장값을 요청 언어에 맞춰 표시한다."""
    try:
        hour, minute = (int(part) for part in (value or "").split(":", 1))
        return f"{hour:02d}:{minute:02d}" if get_lang() == "en" else f"{hour}시 {minute:02d}분"
    except (TypeError, ValueError):
        return value or ""


def _date_label(value: date, *, include_year: bool = False) -> str:
    """라이트닝 날짜를 한국어·영어 화면에 맞춰 표시한다."""
    if get_lang() == "en":
        return f"{value:%B} {value.day}, {value.year}" if include_year else f"{value:%B} {value.day}"
    return f"{value:%Y년 %m월 %d일}" if include_year else f"{value:%m월 %d일}"


def _venue_label(light_session) -> str:
    return (light_session.venue_en if get_lang() == "en" and light_session.venue_en
            else light_session.venue)


_DEFAULT_APPLICATION_NOTICE_KO = """라이트닝토크 신청은 당일에만 가능하며 선착순 8명입니다.
16:30분에 메일로 합격 여부가 나갑니다.
신청 시에는 문서가 없어도 되나, 발표 시에는 있어야 합니다 (구글 슬라이드, PDF).
진행 장소와 시간: 신공학관 4층 4142호 17:20 ~ 18:00"""
_DEFAULT_APPLICATION_NOTICE_EN = """Lightning Talk applications are available on the day only, with up to eight applicants.
Acceptance results are sent by email at 16:30.
Presentation material is not required when applying, but is required for presenting (Google Slides or PDF).
Venue and time: Room 4142, 4F New Engineering Building, 17:20–18:00."""


def _application_notice(value: str = "", value_en: str = "") -> str:
    """저장된 공지의 요청 언어 버전. 기본 한국어 문구는 영문을 자동 제공한다."""
    ko, en = (value or "").strip(), (value_en or "").strip()
    if get_lang() == "en":
        if en:
            return en
        # 기존에 기본 한국어 공지만 저장한 환경도 영어 전환 시 자연스럽게 번역한다.
        if not ko or " ".join(ko.split()) == " ".join(_DEFAULT_APPLICATION_NOTICE_KO.split()):
            return _DEFAULT_APPLICATION_NOTICE_EN
    return ko or t(_DEFAULT_APPLICATION_NOTICE_KO, _DEFAULT_APPLICATION_NOTICE_EN)


def _application_for(db, session_id: int, identity):
    rows = db.exec(select(LightningApplication).where(
        LightningApplication.session_id == session_id,
    ))
    for app in rows:
        if identity.pycon_id and app.applicant_pycon_id == identity.pycon_id:
            return app
        if not app.applicant_pycon_id and app.applicant_email.lower() == identity.email.lower():
            return app
    return None


def _status_label(status):
    return {
        LightningStatus.PENDING: t("검토 대기", "Pending"),
        LightningStatus.WAITLIST: t("대기자", "Waitlist"),
        LightningStatus.ACCEPTED: t("합격", "Accepted"),
        LightningStatus.REJECTED: t("불합격", "Not accepted"),
    }[status]


def _light_form(light_session, application=None, default_name: str = ""):
    """날짜별 신청·수정 폼."""
    if application:
        heading = t("신청 내용", "Your application")
        button = t("신청 내용 수정", "Update application")
        action = f"/light/{light_session.id}/update"
        title = application.title
        description = application.description
        material = application.presentation_url
        speaker_name = application.applicant_name
        status = P(f"{t('상태', 'Status')}: {_status_label(application.status)}",
                   cls="light-status")
    else:
        is_waitlist = not light_session.is_open
        heading = t("대기자 신청", "Join the waitlist") if is_waitlist else t("라이트닝토크 신청", "Apply for Lightning Talk")
        button = t("대기자로 신청하기", "Join waitlist") if is_waitlist else t("신청하기", "Apply")
        action = f"/light/{light_session.id}/apply"
        title = description = material = ""
        speaker_name = default_name
        status = None
    return Section(
        H2(f"{_date_label(light_session.session_date)} · {heading}"),
        P(" · ".join(x for x in [_time_label(light_session.starts_at), _venue_label(light_session)] if x),
          cls="light-when"),
        P(light_session.description, cls="field-help") if light_session.description else None,
        Div(
            P(t("신청 마감", "APPLICATIONS CLOSED"), cls="light-closed-title"),
            P(t("현재 신청은 마감되었습니다. 지금 신청하면 대기자로 등록되며, 최종 참여 여부는 운영 상황에 따라 안내됩니다.",
                "Applications are closed. New submissions join the waitlist; final participation is announced by the organizers.")),
            cls="light-closed-notice",
        ) if not light_session.is_open and not application else None,
        status,
        Div(
            Form(
                field(t("이름 또는 별명", "Name or nickname"), "speaker_name", value=speaker_name,
                      placeholder=t("운영진이 확인할 이름 또는 별명을 입력해 주세요.",
                                    "Enter the name or nickname the event team should use.")),
                field(t("발표 제목", "Talk title"), "title", value=title,
                      placeholder=t("예: 내가 파이썬 커뮤니티에서 배운 것", "e.g. What I learned in the Python community")),
                field(t("간단한 소개", "Short description"), "description", value=description,
                      textarea=True, required=False,
                      placeholder=t("발표 내용을 한두 문장으로 소개해 주세요.", "Describe your talk in one or two sentences.")),
                field(t("발표 자료 URL", "Presentation URL"), "presentation_url", value=material,
                      required=False, placeholder="https://docs.google.com/presentation/..."),
                P(t("Google Slides 공유 링크 또는 누구나 열 수 있는 PDF 링크를 입력해 주세요. "
                    "현장에서 운영진이 바로 엽니다.",
                    "Use a shared Google Slides link or a publicly accessible PDF URL. "
                    "The event team opens it on site."), cls="field-help"),
                Button(button, type="submit"), method="post", action=action,
            ),
            cls="light-application",
        ),
        Form(
            Button(t("신청 내역 삭제", "Delete application"), type="submit", cls="danger"),
            method="post", action=f"/light/{light_session.id}/delete",
            onsubmit=f"return confirm('{t('내 라이트닝토크 신청 내역을 삭제할까요?', 'Delete your Lightning Talk application?')}')",
        ) if application else None,
    )


def _next_order(db, session_id: int) -> int:
    applications = list(db.exec(select(LightningApplication).where(
        LightningApplication.session_id == session_id,
    )))
    return max((app.presentation_order or 0 for app in applications), default=0) + 1


def _application_sort_key(application):
    """발표 순서 변경에 사용하는 정렬 키. 불합격자는 항상 마지막."""
    return (
        application.status == LightningStatus.REJECTED,
        application.presentation_order or application.id or 0,
        application.created_at,
    )


def _application_submission_sort_key(application):
    """관리 신청 목록의 기본 정렬 키: 먼저 접수한 신청부터 표시한다."""
    return (application.created_at, application.id or 0)


def _application_display_order(applications):
    """기본은 접수 순서, 운영자가 발표 순서를 바꾸면 그 순서를 우선한다."""
    submitted = sorted(applications, key=_application_submission_sort_key)
    active = [item for item in submitted if item.status != LightningStatus.REJECTED]
    rejected = [item for item in submitted if item.status == LightningStatus.REJECTED]
    # 새 신청에는 접수 순서와 같은 발표 순서가 자동으로 붙는다. 이 값과 달라진
    # 신청은 운영자가 순서를 조정한 것이므로, 지정한 발표 순서로 앞에 표시한다.
    prioritized = [item for position, item in enumerate(active, start=1)
                   if item.presentation_order is not None and item.presentation_order != position]
    unprioritized = [item for position, item in enumerate(active, start=1)
                     if item.presentation_order is None or item.presentation_order == position]
    return sorted(prioritized, key=_application_sort_key) + unprioritized + rejected


def _move_presentation_order(db, application, requested_order: int) -> None:
    """불합격자를 제외한 신청 목록에서 발표 순서를 원하는 번호로 옮긴다."""
    applications = list(db.exec(select(LightningApplication).where(
        LightningApplication.session_id == application.session_id,
    )))
    active = sorted((item for item in applications
                     if item.status != LightningStatus.REJECTED and item.id != application.id),
                    key=_application_sort_key)
    position = max(1, min(requested_order, len(active) + 1))
    active.insert(position - 1, application)
    for order, item in enumerate(active, start=1):
        item.presentation_order, item.updated_at = order, utcnow()
        db.add(item)


def _accepted_on_other_date(db, application, target_session) -> LightningSession | None:
    """양일 중 한 날짜에 확정되면 다른 날짜에는 확정할 수 없다."""
    accepted = list(db.exec(select(LightningApplication).where(
        LightningApplication.status == LightningStatus.ACCEPTED,
    )))
    sessions = {item.id: item for item in lightning_sessions(db)}
    for item in accepted:
        same_owner = ((application.applicant_pycon_id and
                       application.applicant_pycon_id == item.applicant_pycon_id) or
                      (not application.applicant_pycon_id and
                       application.applicant_email.lower() == item.applicant_email.lower()))
        prior = sessions.get(item.session_id)
        if same_owner and prior and prior.id != target_session.id:
            return prior
    return None


def _admin_application_rows(applications, session_id: int):
    """날짜 하나의 관리자 신청 목록 행과 운영 컨트롤."""
    rows = []
    for number, application in enumerate(applications, start=1):
        material = (A(t("자료 열기 ↗", "Open material ↗"), href=application.presentation_url,
                      target="_blank", rel="noreferrer") if application.presentation_url
                    else t("미등록", "Not provided"))
        actions = Div(
            Form(Button(t("합격", "Accept"), type="submit"), method="post",
                 action=f"/admin/light/applications/{application.id}/accept?session_id={session_id}", style="display:inline"), " ",
            Form(Button(t("불합격", "Reject"), type="submit", cls="secondary"), method="post",
                 action=f"/admin/light/applications/{application.id}/reject?session_id={session_id}", style="display:inline"),
            " ",
            Form(Button(t("삭제", "Delete"), type="submit", cls="danger"), method="post",
                 action=f"/admin/light/applications/{application.id}/delete?session_id={session_id}",
                 onsubmit=f"return confirm('{t('이 신청 내역을 삭제할까요?', 'Delete this application?')}')",
                 style="display:inline"),
        )
        order = (Form(Input(type="number", name="presentation_order",
                            value=str(application.presentation_order or number), min="1"),
                      Button(t("발표 순서 저장", "Save presentation order"), type="submit", cls="secondary"),
                      method="post", action=f"/admin/light/applications/{application.id}/order?session_id={session_id}")
                 if application.status != LightningStatus.REJECTED else "—")
        rows.append(Tr(Td(str(number)), Td(application.applicant_name), Td(application.applicant_email),
                       Td(application.title), Td(_status_label(application.status)),
                       Td(order), Td(material), Td(actions),
                       cls="light-application-rejected" if application.status == LightningStatus.REJECTED else ""))
    return rows


def register(app) -> None:
    @app.get("/light/admin")
    def light_operator_login(session):
        """PyCon 로그인 없이 현장 라이트닝 운영 화면으로 들어가는 비밀번호 입구."""
        if session.get("light_operator_authenticated"):
            return RedirectResponse("/admin/light", status_code=303)
        return layout(
            t("라이트닝토크 운영", "Lightning Talk Operations"),
            H1(t("라이트닝토크 운영", "Lightning Talk Operations")),
            P(t("현장 운영 전용 페이지입니다. 비밀번호를 입력해 주세요.",
                "This page is for on-site operators. Enter the password."), cls="field-help"),
            Form(
                field(t("운영 비밀번호", "Operator password"), "password", input_type="password"),
                Button(t("열기", "Open"), type="submit"),
                method="post", action="/light/admin/login",
            ),
            active="/light",
        )

    @app.post("/light/admin/login")
    def light_operator_login_submit(session, password: str = ""):
        configured = get_settings().light_operator_password
        if configured and compare_digest(password or "", configured):
            session["light_operator_authenticated"] = True
            return RedirectResponse("/admin/light", status_code=303)
        return layout(
            t("라이트닝토크 운영", "Lightning Talk Operations"),
            H1(t("라이트닝토크 운영", "Lightning Talk Operations")),
            notice(t("비밀번호가 올바르지 않습니다.", "The password is incorrect."), kind="error"),
            A(t("다시 입력", "Try again"), href="/light/admin", cls="btn secondary"),
            active="/light",
        )

    @app.post("/light/admin/logout")
    def light_operator_logout(session):
        session.pop("light_operator_authenticated", None)
        return RedirectResponse("/light/admin", status_code=303)

    @app.get("/light")
    def light_page(request, session):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        with get_session() as db:
            # 라이트닝토크는 현장 당일에만 보인다. 마감 후에도 대기자 신청을 받는다.
            sessions = [item for item in lightning_sessions(db)
                        if item.session_date == _today()]
            applications = {item.id: _application_for(db, item.id, identity) for item in sessions}
            application_notice = lightning_application_notice(db)
            application_notice_en = lightning_application_notice_en(db)
        default_name = identity.username or identity.email.split("@")[0]
        body = [_light_form(item, applications[item.id], default_name) for item in sessions]
        if not body:
            body = [notice(t("라이트닝토크 신청은 해당 행사일에만 가능합니다.",
                             "Lightning Talk applications are available only on the event day."))]
        return layout(t("라이트닝토크", "Lightning Talk"),
                      H1(t("라이트닝토크 신청", "Lightning Talk Application")),
                      P(_application_notice(application_notice, application_notice_en), cls="light-application-notice"),
                      *body, active="/light")

    @app.post("/light/{light_session_id}/apply")
    def light_apply(request, session, light_session_id: int, speaker_name: str, title: str,
                    description: str = "", presentation_url: str = ""):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        speaker_name, title = (speaker_name or "").strip(), (title or "").strip()
        material = _valid_material_url(presentation_url)
        if not speaker_name or not title or material is None:
            return layout(t("라이트닝토크", "Lightning Talk"),
                          notice(t("이름 또는 별명, 제목, 올바른 http/https 자료 URL을 확인해 주세요.",
                                   "Check the name or nickname, title, and a valid http/https presentation URL."), kind="error"),
                          A(t("돌아가기", "Back"), href="/light", cls="btn secondary"))
        with get_session() as db:
            item = db.get(LightningSession, light_session_id)
            if not item or item.session_date != _today():
                return RedirectResponse("/light", status_code=303)
            if _application_for(db, item.id, identity):
                return RedirectResponse("/light", status_code=303)
            db.add(LightningApplication(
                session_id=item.id, applicant_pycon_id=identity.pycon_id,
                applicant_name=speaker_name,
                applicant_email=identity.email, applicant_username=identity.username,
                title=title, description=(description or "").strip(), presentation_url=material,
                status=(LightningStatus.PENDING if item.is_open else LightningStatus.WAITLIST),
                presentation_order=_next_order(db, item.id),
            ))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        return RedirectResponse("/light", status_code=303)

    @app.post("/light/{light_session_id}/update")
    def light_update(request, session, light_session_id: int, speaker_name: str, title: str,
                     description: str = "", presentation_url: str = ""):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        speaker_name, title = (speaker_name or "").strip(), (title or "").strip()
        material = _valid_material_url(presentation_url)
        if not speaker_name or not title or material is None:
            return RedirectResponse("/light", status_code=303)
        with get_session() as db:
            application = _application_for(db, light_session_id, identity)
            if application:
                application.applicant_name, application.title = speaker_name, title
                application.description = (description or "").strip()
                application.presentation_url, application.updated_at = material, utcnow()
                db.add(application)
                db.commit()
        return RedirectResponse("/light", status_code=303)

    @app.post("/light/{light_session_id}/delete")
    def light_delete(request, session, light_session_id: int):
        """참가자는 본인이 등록한 라이트닝토크 신청 내역만 삭제할 수 있다."""
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        with get_session() as db:
            application = _application_for(db, light_session_id, identity)
            if application:
                db.delete(application)
                db.commit()
        return RedirectResponse("/light", status_code=303)

    @app.get("/admin/light")
    def admin_light(session):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            sessions = lightning_sessions(db)
            common_qrs = lightning_qrs(db)[:1]
            application_notice = lightning_application_notice(db)
            application_notice_en = lightning_application_notice_en(db)
        parts = []
        for item in sessions:
            parts.append(Section(
                H2(f"{item.session_date:%Y.%m.%d} · {t('신청 열림', 'Open') if item.is_open else t('신청 마감 · 대기자 접수', 'Closed · Waitlist open')}"),
                Form(field(t("전광판 제목", "Board title"), "board_title", value=item.board_title,
                           required=False,
                           placeholder=t("예: 파이콘 한국 라이트닝 토크", "e.g. PyCon Korea Lightning Talk")),
                     field(t("시작 예정 시각", "Start time"), "starts_at", value=item.starts_at,
                           input_type="time", required=False),
                     field(t("장소", "Venue"), "venue", value=item.venue, required=False),
                     field(t("영문 장소", "Venue in English"), "venue_en", value=item.venue_en,
                           required=False, placeholder="e.g. Room 4142, 4F New Engineering Building"),
                     field(t("안내 문구", "Board description"), "description", value=item.description,
                           textarea=True, required=False),
                     Button(t("설정 저장", "Save settings"), type="submit"), method="post",
                     action=f"/admin/light/{item.id}/update"),
                Form(Button(t("신청 마감", "Close applications") if item.is_open else t("신청 재개", "Reopen applications"),
                            type="submit", cls="secondary"), method="post", action=f"/admin/light/{item.id}/toggle"),
                P(t("현재 신청 마감 상태입니다. 새 신청은 대기자로 등록됩니다.",
                    "Applications are currently closed. New submissions join the waitlist."),
                  cls="light-admin-closed") if not item.is_open else None,
                P(A(t("이 날짜의 신청 목록 보기", "View applications for this date"),
                    href=f"/admin/light/applications?session_id={item.id}", cls="btn secondary")),
                cls="light-admin-session"))
        return _admin_layout(t("라이트닝토크", "Lightning Talk"),
                             H2(t("라이트닝토크 날짜 추가", "Add Lightning Talk Date")),
                             Form(field(t("날짜", "Date"), "session_date", input_type="date"),
                                  Button(t("날짜 추가", "Add date"), type="submit"), method="post", action="/admin/light"),
                             Section(
                                 H2(t("라이트닝토크 데모 데이터", "Lightning Talk demo data")),
                                 P(t("15·16일 세션과 합격·검토 대기·대기자·불합격 신청 예시를 만듭니다. "
                                     "기존 라이트닝 세션과 신청 목록은 교체됩니다.",
                                     "Creates 15th/16th sessions with accepted, pending, waitlisted, and rejected examples. "
                                     "Existing Lightning Talk sessions and applications are replaced."), cls="field-help"),
                                 Form(Button(t("데모 데이터 채우기", "Seed demo data"), type="submit", cls="secondary"),
                                      method="post", action="/admin/light/seed",
                                      onsubmit=f"return confirm('{t('기존 라이트닝토크 세션과 신청 목록을 교체합니다. 계속할까요?', 'This replaces existing Lightning Talk sessions and applications. Continue?')}')"),
                             ),
                             P(A(t("라이트닝 전광판 열기", "Open Lightning Board"), href="/light/board", target="_blank", cls="btn secondary")),
                             Section(
                                 H2(t("공통 신청 공지", "Shared application notice")),
                                 P(t("15일·16일 신청 화면에 같은 공지가 표시됩니다.",
                                     "The same notice appears on both application dates."), cls="field-help"),
                                 Form(field(t("공지", "Notice"), "application_notice",
                                            value=application_notice or _DEFAULT_APPLICATION_NOTICE_KO, textarea=True,
                                            required=False),
                                      field(t("영문 공지", "Notice in English"), "application_notice_en",
                                            value=application_notice_en or _DEFAULT_APPLICATION_NOTICE_EN, textarea=True,
                                            required=False),
                                      Button(t("공지 저장", "Save notice"), type="submit"), method="post",
                                      action="/admin/light/notice"),
                             ),
                             Section(
                                 H2(t("공통 신청 QR", "Shared application QR")),
                                 P(t("당일 라이트닝 전광판에만 표시되는 QR 코드입니다.",
                                     "This QR code appears on the current-day Lightning Talk board."),
                                   cls="field-help"),
                                 Div(*[Div(Img(src=qr.image_url, alt=qr.caption or "QR",
                                                cls="light-qr-preview"),
                                            P(qr.caption or "—"),
                                            Form(Button(t("삭제", "Delete"), type="submit", cls="danger"),
                                                 method="post", action=f"/admin/light/qr/{qr.id}/delete"),
                                            cls="qr-block") for qr in common_qrs], cls="qr-grid"),
                                 Form(field(t("QR 이미지 파일", "QR image file"), "image_file",
                                            input_type="file", required=False),
                                      field(t("또는 QR 이미지 URL", "Or QR image URL"), "image_url",
                                            placeholder="https://...", required=False),
                                      field(t("설명", "Caption"), "caption", required=False),
                                      Button(t("QR 저장", "Save QR"), type="submit"), method="post",
                                      action="/admin/light/board-qr", enctype="multipart/form-data"),
                             ),
                             *parts)

    @app.post("/admin/light/seed")
    def admin_light_seed(session):
        """라이트닝 운영 화면을 빠르게 확인할 수 있는 예시 세션·신청 목록을 채운다."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            # 신청 → 날짜별 QR → 세션 순으로 지워 FK 제약을 지킨다. 공통 전광판 QR은 보존.
            for application in db.exec(select(LightningApplication)):
                db.delete(application)
            for qr in db.exec(select(LightningQR).where(LightningQR.session_id != None)):  # noqa: E711
                db.delete(qr)
            for item in db.exec(select(LightningSession)):
                db.delete(item)
            db.commit()

            first = LightningSession(
                session_date=date(2026, 8, 15), starts_at="17:20",
                venue="신공학관 4층 4142호", venue_en="Room 4142, 4F New Engineering Building",
                description="정규 세션 종료 후 진행됩니다.", is_open=True,
            )
            second = LightningSession(
                session_date=date(2026, 8, 16), starts_at="17:20",
                venue="신공학관 4층 4142호", venue_en="Room 4142, 4F New Engineering Building",
                description="정규 세션 종료 후 진행됩니다.", is_open=False,
            )
            db.add(first); db.add(second); db.commit(); db.refresh(first); db.refresh(second)
            db.add_all([
                LightningApplication(session_id=first.id, applicant_email="minji@example.com",
                    applicant_name="민지", title="파이썬으로 시작한 작은 자동화", description="반복 업무를 줄인 경험입니다.",
                    presentation_url="https://docs.google.com/presentation/d/example", status=LightningStatus.ACCEPTED,
                    presentation_order=1),
                LightningApplication(session_id=first.id, applicant_email="junho@example.com",
                    applicant_name="준호", title="커뮤니티에서 만난 첫 오픈소스", description="함께 기여하며 배운 이야기입니다.",
                    status=LightningStatus.PENDING, presentation_order=2),
                LightningApplication(session_id=first.id, applicant_email="seoyeon@example.com",
                    applicant_name="서연", title="파이썬으로 만든 나만의 도구", description="작지만 유용한 도구 소개입니다.",
                    status=LightningStatus.WAITLIST, presentation_order=3),
                LightningApplication(session_id=first.id, applicant_email="dohyun@example.com",
                    applicant_name="도현", title="파이썬 첫 발표 도전기", status=LightningStatus.REJECTED,
                    presentation_order=99),
                LightningApplication(session_id=second.id, applicant_email="yuna@example.com",
                    applicant_name="유나", title="파이썬과 함께한 취미 프로젝트", status=LightningStatus.WAITLIST,
                    presentation_order=1),
            ])
            db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.get("/admin/light/applications")
    def admin_light_applications(session, session_id: int = 0):
        """날짜 선택형 라이트닝토크 신청 목록·합격·순서 운영 화면."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            sessions = lightning_sessions(db)
            selected = next((item for item in sessions if item.id == session_id),
                            sessions[0] if sessions else None)
            applications = (_application_display_order(list(db.exec(select(LightningApplication).where(
                LightningApplication.session_id == selected.id))))
                            if selected else [])
        date_links = Div(*[
            A(f"{item.session_date:%m월 %d일}",
              href=f"/admin/light/applications?session_id={item.id}",
              cls="btn" if selected and item.id == selected.id else "btn secondary")
            for item in sessions
        ], cls="light-date-tabs")
        table = (Table(Thead(Tr(Th(t("번호", "No.")), Th(t("신청자", "Applicant")), Th(t("이메일", "Email")),
                                Th(t("발표 제목", "Title")), Th(t("상태", "Status")),
                                Th(t("발표 순서", "Presentation order")), Th(t("발표 자료", "Material")),
                                Th(t("작업", "Actions")))),
                       *_admin_application_rows(applications, selected.id), cls="schedule")
                 if applications else P(t("이 날짜에는 신청이 없습니다.", "No applications for this date.")))
        return _admin_layout(t("라이트닝토크 신청 목록", "Lightning Talk Applications"),
                             H2(t("신청 목록", "Applications")),
                             P(A(t("라이트닝토크 설정으로", "Lightning Talk settings"), href="/admin/light", cls="btn secondary")),
                             date_links,
                             H2(f"{selected.session_date:%Y년 %m월 %d일}" if selected else t("날짜 없음", "No dates")),
                             table)

    @app.post("/admin/light")
    def admin_light_create(session, session_date: str):
        if (redir := _require_admin(session)):
            return redir
        try:
            day = date.fromisoformat(session_date)
        except ValueError:
            return RedirectResponse("/admin/light", status_code=303)
        with get_session() as db:
            if not db.exec(select(LightningSession).where(LightningSession.session_date == day)).first():
                db.add(LightningSession(session_date=day))
                db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.post("/admin/light/{light_session_id}/update")
    def admin_light_update(session, light_session_id: int, board_title: str = "", starts_at: str = "",
                           venue: str = "", venue_en: str = "", description: str = "",
                           application_notice: str = ""):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            item = db.get(LightningSession, light_session_id)
            if item:
                item.board_title = (board_title or "").strip()
                item.starts_at, item.venue = (starts_at or "").strip(), (venue or "").strip()
                item.venue_en = (venue_en or "").strip()
                item.description, item.updated_at = (description or "").strip(), utcnow()
                db.add(item); db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.post("/admin/light/notice")
    def admin_light_notice(session, application_notice: str = "", application_notice_en: str = ""):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            setting = db.get(LightningSetting, 1) or LightningSetting(id=1)
            setting.application_notice = (application_notice or "").strip()
            setting.application_notice_en = (application_notice_en or "").strip()
            setting.updated_at = utcnow()
            db.add(setting)
            db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.post("/admin/light/{light_session_id}/toggle")
    def admin_light_toggle(session, light_session_id: int):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            item = db.get(LightningSession, light_session_id)
            if item:
                item.is_open, item.updated_at = not item.is_open, utcnow()
                db.add(item); db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.post("/admin/light/applications/{application_id}/accept")
    def admin_light_accept(session, application_id: int, session_id: int = 0):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            application = db.get(LightningApplication, application_id)
            target = db.get(LightningSession, application.session_id) if application else None
            previous = _accepted_on_other_date(db, application, target) if application and target else None
            if previous:
                return _admin_layout(t("라이트닝토크", "Lightning Talk"),
                    notice(t(f"이 신청자는 {previous.session_date:%m월 %d일} 참여자로 이미 확정되어 다른 날짜에 합격 처리할 수 없습니다.",
                             f"This applicant is already accepted for {previous.session_date:%b %d} and cannot be accepted again."), kind="error"),
                    A(t("돌아가기", "Back"),
                      href=f"/admin/light/applications?session_id={session_id}", cls="btn secondary"))
            if application:
                application.status = LightningStatus.ACCEPTED
                if application.presentation_order is None:
                    application.presentation_order = _next_order(db, application.session_id)
                application.updated_at = utcnow(); db.add(application); db.commit()
        return RedirectResponse(f"/admin/light/applications?session_id={session_id}", status_code=303)

    @app.post("/admin/light/applications/{application_id}/reject")
    def admin_light_reject(session, application_id: int, session_id: int = 0):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            application = db.get(LightningApplication, application_id)
            if application:
                application.status = LightningStatus.REJECTED
                # 불합격자는 발표 순서상 맨 아래로 이동한다.
                application.presentation_order = _next_order(db, application.session_id)
                application.updated_at = utcnow(); db.add(application); db.commit()
        return RedirectResponse(f"/admin/light/applications?session_id={session_id}", status_code=303)

    @app.post("/admin/light/applications/{application_id}/delete")
    def admin_light_application_delete(session, application_id: int, session_id: int = 0):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            application = db.get(LightningApplication, application_id)
            if application:
                db.delete(application)
                db.commit()
        return RedirectResponse(f"/admin/light/applications?session_id={session_id}", status_code=303)

    @app.post("/admin/light/applications/{application_id}/order")
    def admin_light_order(session, application_id: int, presentation_order: int = 0,
                          session_id: int = 0):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            application = db.get(LightningApplication, application_id)
            if application and application.status != LightningStatus.REJECTED and presentation_order > 0:
                _move_presentation_order(db, application, presentation_order)
                db.commit()
        return RedirectResponse(f"/admin/light/applications?session_id={session_id}", status_code=303)

    @app.post("/admin/light/{light_session_id}/qr")
    async def admin_light_qr(session, light_session_id: int, image_url: str = "", caption: str = "",
                             sort_order: int = 0, image_file: UploadFile = None):
        if (redir := _require_admin(session)):
            return redir
        try:
            image_url = await save_image(image_file) or normalize_image_url(image_url)
        except UploadError as exc:
            return _admin_layout(t("라이트닝토크", "Lightning Talk"),
                                 notice(str(exc), kind="error"),
                                 A(t("돌아가기", "Back"), href="/admin/light", cls="btn secondary"))
        if image_url:
            with get_session() as db:
                db.add(LightningQR(session_id=light_session_id, image_url=image_url,
                                   caption=(caption or "").strip(), sort_order=sort_order))
                db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.post("/admin/light/board-qr")
    async def admin_light_board_qr(session, image_url: str = "", caption: str = "",
                                   image_file: UploadFile = None):
        """양일 공통의 단일 신청 QR을 저장한다."""
        if (redir := _require_admin(session)):
            return redir
        try:
            new_url = await save_image(image_file) or normalize_image_url(image_url)
        except UploadError as exc:
            return _admin_layout(t("라이트닝토크", "Lightning Talk"),
                                 notice(str(exc), kind="error"),
                                 A(t("돌아가기", "Back"), href="/admin/light", cls="btn secondary"))
        if new_url:
            with get_session() as db:
                qr = lightning_qrs(db)[0] if lightning_qrs(db) else LightningQR(session_id=None,
                                                                                  image_url=new_url)
                old_url = qr.image_url
                qr.image_url, qr.caption, qr.updated_at = new_url, (caption or "").strip(), utcnow()
                db.add(qr)
                db.commit()
                if old_url != new_url:
                    delete_local_image(old_url)
        return RedirectResponse("/admin/light", status_code=303)

    @app.post("/admin/light/qr/{qr_id}/delete")
    def admin_light_qr_delete(session, qr_id: int):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            qr = db.get(LightningQR, qr_id)
            if qr:
                delete_local_image(qr.image_url)
                db.delete(qr); db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.get("/light/board")
    def light_board(session, board_lang: str = ""):
        if board_lang in {"ko", "en"}:
            set_lang(board_lang)
        note_identity(identity_from_session(session))
        with get_session() as db:
            qrs = lightning_qrs(db)[:1]
            language_interval = board_language_interval(db)
        # 전광판은 신청 QR만 빠르게 인지하는 용도다. 날짜·시간·장소·안내문·QR 캡션 등
        # 관리자 입력 내용은 노출하지 않는다.
        qr_content = Div(
            *[Img(src=qr.image_url, alt=t("라이트닝 토크 신청 QR 코드", "Lightning Talk application QR code"),
                  cls="light-board-qr-img") for qr in qrs if qr.image_url],
            cls="light-board-qr-only",
        )
        return layout(t("라이트닝 토크", "Lightning Talk"),
                      H1(t("라이트닝 토크", "Lightning Talk"), cls="light-board-title"),
                      qr_content,
                      board_language_auto_switch(language_interval),
                      chrome=False, main_cls="light-board-content", body_cls="light-board")
