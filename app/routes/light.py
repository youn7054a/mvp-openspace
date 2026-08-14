"""라이트닝토크: 신청(/light), 관리자(/admin/light), 안내 전광판(/light/board)."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from fasthtml.common import A, Button, Div, Form, H1, H2, Img, Input, P, RedirectResponse, Section, Table, Td, Th, Thead, Tr
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..auth import identity_from_session, login_required_page, note_identity, resolve_identity
from ..components import field, layout, notice
from ..database import get_session
from ..i18n import t
from ..models import LightningApplication, LightningQR, LightningSession, LightningStatus, utcnow
from ..queries import lightning_qrs, lightning_sessions


def _admin_layout(title, *content):
    # admin 모듈 초기화 후에만 가져와 순환 import를 피한다.
    from .admin import _admin_layout as base_layout
    return base_layout(title, *content)


def _require_admin(session):
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
    """신청 가능 날짜 판정용 — 테스트에서 고정할 수 있게 분리."""
    return date.today()


def _time_label(value: str) -> str:
    """HH:MM 저장값을 한국어 표시용 'H시 MM분'으로 바꾼다."""
    try:
        hour, minute = (int(part) for part in (value or "").split(":", 1))
        return f"{hour}시 {minute:02d}분"
    except (TypeError, ValueError):
        return value or ""


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
        heading = t("라이트닝토크 신청", "Apply for Lightning Talk")
        button = t("신청하기", "Apply")
        action = f"/light/{light_session.id}/apply"
        title = description = material = ""
        speaker_name = default_name
        status = None
    return Section(
        H2(f"{light_session.session_date:%m}월 {light_session.session_date:%d}일 · {heading}"),
        P(" · ".join(x for x in [_time_label(light_session.starts_at), light_session.venue] if x),
          cls="light-when"),
        P(light_session.description, cls="field-help") if light_session.description else None,
        status,
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
        ), cls="light-application",
    )


def _next_order(db, session_id: int) -> int:
    accepted = list(db.exec(select(LightningApplication).where(
        LightningApplication.session_id == session_id,
        LightningApplication.status == LightningStatus.ACCEPTED,
    )))
    return max((app.presentation_order or 0 for app in accepted), default=0) + 1


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
    for application in applications:
        material = (A(t("자료 열기 ↗", "Open material ↗"), href=application.presentation_url,
                      target="_blank", rel="noreferrer") if application.presentation_url
                    else t("미등록", "Not provided"))
        actions = Div(
            Form(Button(t("합격", "Accept"), type="submit"), method="post",
                 action=f"/admin/light/applications/{application.id}/accept?session_id={session_id}", style="display:inline"), " ",
            Form(Button(t("불합격", "Reject"), type="submit", cls="secondary"), method="post",
                 action=f"/admin/light/applications/{application.id}/reject?session_id={session_id}", style="display:inline"),
        )
        order = (Form(Input(type="number", name="presentation_order",
                            value=str(application.presentation_order or ""), min="1"),
                      Button(t("순서 저장", "Save order"), type="submit", cls="secondary"),
                      method="post", action=f"/admin/light/applications/{application.id}/order?session_id={session_id}")
                 if application.status == LightningStatus.ACCEPTED else "—")
        rows.append(Tr(Td(application.applicant_name), Td(application.applicant_email),
                       Td(application.title), Td(_status_label(application.status)),
                       Td(order), Td(material), Td(actions)))
    return rows


def register(app) -> None:
    @app.get("/light")
    def light_page(request, session):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        with get_session() as db:
            # 라이트닝토크는 현장 당일 접수만 허용한다.
            sessions = [item for item in lightning_sessions(db)
                        if item.is_open and item.session_date == _today()]
            applications = {item.id: _application_for(db, item.id, identity) for item in sessions}
        default_name = identity.username or identity.email.split("@")[0]
        body = [_light_form(item, applications[item.id], default_name) for item in sessions]
        if not body:
            body = [notice(t("라이트닝토크 신청은 해당 행사일에만 가능합니다.",
                             "Lightning Talk applications are available only on the event day."))]
        return layout(t("라이트닝토크", "Lightning Talk"),
                      H1(t("라이트닝토크 신청", "Lightning Talk Application")),
                      *([P(sessions[0].application_notice or t(
                          "당일 신청을 받습니다. 최종 참여 여부는 내부 운영 기준에 따라 결정됩니다.",
                          "Applications are accepted on the day. Final participation follows internal operating guidelines."),
                          cls="light-application-notice")] if sessions else []),
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
            if not item or not item.is_open or item.session_date != _today():
                return RedirectResponse("/light", status_code=303)
            if _application_for(db, item.id, identity):
                return RedirectResponse("/light", status_code=303)
            db.add(LightningApplication(
                session_id=item.id, applicant_pycon_id=identity.pycon_id,
                applicant_name=speaker_name,
                applicant_email=identity.email, applicant_username=identity.username,
                title=title, description=(description or "").strip(), presentation_url=material,
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

    @app.get("/admin/light")
    def admin_light(session):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            sessions = lightning_sessions(db)
            qrs = {item.id: lightning_qrs(db, item.id) for item in sessions}
        parts = []
        for item in sessions:
            qr_forms = [Div(Img(src=qr.image_url, alt=qr.caption or "QR", cls="light-qr-preview"),
                            P(qr.caption or "—"),
                            Form(Button(t("삭제", "Delete"), type="submit", cls="danger"),
                                 method="post", action=f"/admin/light/qr/{qr.id}/delete"), cls="qr-block")
                        for qr in qrs[item.id]]
            parts.append(Section(
                H2(f"{item.session_date:%Y.%m.%d} · {t('신청 열림', 'Open') if item.is_open else t('신청 닫힘', 'Closed')}"),
                Form(field(t("전광판 제목", "Board title"), "board_title", value=item.board_title,
                           required=False,
                           placeholder=t("예: 파이콘 한국 라이트닝 토크", "e.g. PyCon Korea Lightning Talk")),
                     field(t("신청 안내 문구", "Application notice"), "application_notice",
                           value=item.application_notice, textarea=True, required=False,
                           placeholder=t("예: 당일 신청을 받습니다. 최종 참여 여부는 내부 운영 기준에 따라 결정됩니다.",
                                         "e.g. Applications are accepted on the day.")),
                     field(t("시작 예정 시각", "Start time"), "starts_at", value=item.starts_at,
                           input_type="time", required=False),
                     field(t("장소", "Venue"), "venue", value=item.venue, required=False),
                     field(t("안내 문구", "Board description"), "description", value=item.description,
                           textarea=True, required=False),
                     Button(t("설정 저장", "Save settings"), type="submit"), method="post",
                     action=f"/admin/light/{item.id}/update"),
                Form(Button(t("신청 닫기", "Close applications") if item.is_open else t("신청 열기", "Open applications"),
                            type="submit", cls="secondary"), method="post", action=f"/admin/light/{item.id}/toggle"),
                P(A(t("이 날짜의 신청 목록 보기", "View applications for this date"),
                    href=f"/admin/light/applications?session_id={item.id}", cls="btn secondary")),
                H2(t("전광판 QR", "Board QR")),
                Div(*qr_forms, cls="qr-grid"),
                Form(field(t("QR 이미지 URL", "QR image URL"), "image_url", placeholder="https://..."),
                     field(t("설명", "Caption"), "caption", required=False),
                     field(t("정렬 순서", "Sort order"), "sort_order", value="0", input_type="number", required=False),
                     Button(t("QR 추가", "Add QR"), type="submit"), method="post",
                     action=f"/admin/light/{item.id}/qr"), cls="light-admin-session"))
        return _admin_layout(t("라이트닝토크", "Lightning Talk"),
                             H2(t("라이트닝토크 날짜 추가", "Add Lightning Talk Date")),
                             Form(field(t("날짜", "Date"), "session_date", input_type="date"),
                                  Button(t("날짜 추가", "Add date"), type="submit"), method="post", action="/admin/light"),
                             P(A(t("라이트닝 전광판 열기", "Open Lightning Board"), href="/light/board", target="_blank", cls="btn secondary")),
                             *parts)

    @app.get("/admin/light/applications")
    def admin_light_applications(session, session_id: int = 0):
        """날짜 선택형 라이트닝토크 신청 목록·합격·순서 운영 화면."""
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            sessions = lightning_sessions(db)
            selected = next((item for item in sessions if item.id == session_id),
                            sessions[0] if sessions else None)
            applications = (list(db.exec(select(LightningApplication).where(
                LightningApplication.session_id == selected.id).order_by(
                LightningApplication.presentation_order, LightningApplication.created_at)))
                            if selected else [])
        date_links = Div(*[
            A(f"{item.session_date:%m월 %d일}",
              href=f"/admin/light/applications?session_id={item.id}",
              cls="btn" if selected and item.id == selected.id else "btn secondary")
            for item in sessions
        ], cls="light-date-tabs")
        table = (Table(Thead(Tr(Th(t("신청자", "Applicant")), Th(t("이메일", "Email")),
                                Th(t("발표 제목", "Title")), Th(t("상태", "Status")),
                                Th(t("순서", "Order")), Th(t("발표 자료", "Material")),
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
                           venue: str = "", description: str = "", application_notice: str = ""):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            item = db.get(LightningSession, light_session_id)
            if item:
                item.board_title = (board_title or "").strip()
                item.application_notice = (application_notice or "").strip()
                item.starts_at, item.venue = (starts_at or "").strip(), (venue or "").strip()
                item.description, item.updated_at = (description or "").strip(), utcnow()
                db.add(item); db.commit()
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
                application.status, application.presentation_order = LightningStatus.REJECTED, None
                application.updated_at = utcnow(); db.add(application); db.commit()
        return RedirectResponse(f"/admin/light/applications?session_id={session_id}", status_code=303)

    @app.post("/admin/light/applications/{application_id}/order")
    def admin_light_order(session, application_id: int, presentation_order: int = 0,
                          session_id: int = 0):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            application = db.get(LightningApplication, application_id)
            if application and application.status == LightningStatus.ACCEPTED and presentation_order > 0:
                application.presentation_order, application.updated_at = presentation_order, utcnow()
                db.add(application); db.commit()
        return RedirectResponse(f"/admin/light/applications?session_id={session_id}", status_code=303)

    @app.post("/admin/light/{light_session_id}/qr")
    def admin_light_qr(session, light_session_id: int, image_url: str, caption: str = "", sort_order: int = 0):
        if (redir := _require_admin(session)):
            return redir
        image_url = _valid_material_url(image_url)
        if image_url:
            with get_session() as db:
                db.add(LightningQR(session_id=light_session_id, image_url=image_url,
                                   caption=(caption or "").strip(), sort_order=sort_order))
                db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.post("/admin/light/qr/{qr_id}/delete")
    def admin_light_qr_delete(session, qr_id: int):
        if (redir := _require_admin(session)):
            return redir
        with get_session() as db:
            qr = db.get(LightningQR, qr_id)
            if qr:
                db.delete(qr); db.commit()
        return RedirectResponse("/admin/light", status_code=303)

    @app.get("/light/board")
    def light_board(session):
        note_identity(identity_from_session(session))
        with get_session() as db:
            # 신청을 닫아도 전광판 안내(일시·장소·QR)는 계속 보여 준다.
            sessions = lightning_sessions(db)
            qr_map = {item.id: lightning_qrs(db, item.id) for item in sessions}
        board_title = next((item.board_title for item in sessions if item.board_title),
                           t("파이콘 한국 라이트닝 토크", "PyCon Korea Lightning Talk"))
        cards = []
        for item in sessions:
            qrs = qr_map[item.id]
            cards.append(Section(
                H2(f"{item.session_date:%Y년 %m월 %d일}"),
                P(" · ".join(x for x in [_time_label(item.starts_at), item.venue] if x), cls="light-board-when"),
                P(item.description or t("정규 세션 종료 후 진행됩니다.", "Held after the regular sessions."), cls="light-board-description"),
                Div(*[Div(Img(src=qr.image_url, alt=qr.caption or "QR", cls="light-board-qr-img"),
                             P(qr.caption, cls="light-board-qr-caption"), cls="light-board-qr") for qr in qrs],
                    cls="light-board-qrs"), cls="light-board-card"))
        return layout(t("라이트닝 토크", "Lightning Talk"),
                      H1(board_title),
                      P(t("현장 신청을 받습니다. 정규 세션 종료 후 진행됩니다.",
                          "On-site applications are open. Held after the regular sessions."), cls="light-board-lead"),
                      *(cards if cards else [notice(t("현재 안내할 라이트닝토크가 없습니다.", "No Lightning Talk is currently announced."))]),
                      chrome=False, main_cls="light-board-content", body_cls="light-board")
