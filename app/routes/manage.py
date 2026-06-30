"""내 주제 관리 (Manage My Topic): /manage/{topic_id} — 신원(PyCon) 소유 확인."""
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
    Section,
    Small,
)
from starlette.datastructures import UploadFile

from ..auth import login_required_page, resolve_identity
from ..components import (
    account_field,
    layout,
    notice,
    topic_text_fields,
)
from ..database import get_session
from ..i18n import t
from ..models import Room, Timeslot, utcnow
from ..queries import entry_for_topic, get_owned_topic
from ..uploads import (
    UploadError,
    delete_local_image,
    normalize_image_url,
    save_image,
)

PANEL_ID = "manage-panel"


def _schedule_status(session, topic):
    """현재 배정 상태 + '타임테이블에서 자리 잡기' 링크.

    실제 등록/변경/취소는 타임테이블 뷰(`/schedule?topic=`)에서 처리한다.
    """
    entry = entry_for_topic(session, topic.id)
    children = [H2(t("타임테이블", "Timetable"))]
    if entry:
        room = session.get(Room, entry.room_id)
        ts = session.get(Timeslot, entry.timeslot_id)
        label = f"{room.name if room else '?'} · {ts.time_label if ts else '?'}"
        children.append(notice(f"{t('현재 배정', 'Scheduled')}: {label}",
                               kind="success"))
    else:
        children.append(P(t("아직 타임테이블에 자리를 잡지 않았어요.",
                            "Not placed on the timetable yet."), cls="schedule-hint"))
    children.append(A(
        t("타임테이블에서 자리 잡기", "Place on the timetable"),
        href=f"/schedule?topic={topic.id}#sched", cls="btn"))
    return Section(*children, cls="schedule-section")


def _image_edit_fields(topic):
    """주제 대표 이미지 편집 (Edit topic image) — 현재 이미지·교체·제거."""
    children = [Legend(t("주제 대표 이미지", "Topic image"))]
    if topic.image_url:
        children.append(Div(
            Img(src=topic.image_url, alt=t("현재 이미지", "Current image"),
                cls="edit-thumb"),
            Label(
                Input(type="checkbox", name="remove_image", value="1"),
                " " + t("사진 제거", "Remove image"), cls="checkbox-label",
            ),
            cls="current-image",
        ))
    else:
        children.append(Small(t("아직 등록된 이미지가 없습니다.", "No image yet."),
                              cls="field-help"))
    children += [
        Div(
            Label(t("새 파일 업로드", "Upload new"), fr="m-image_file"),
            Input(id="m-image_file", name="image_file", type="file",
                  accept="image/png,image/jpeg,image/gif,image/webp"),
            cls="field",
        ),
        Div(
            Label(t("또는 이미지 URL", "or Image URL"), fr="m-image_url"),
            Input(id="m-image_url", name="image_url", type="url", required=False,
                  placeholder="https://example.com/cover.png"),
            cls="field",
        ),
    ]
    return Fieldset(*children, cls="image-fields")


def _panel(session, topic, *, msg=None):
    """관리 패널 (Manage panel) — HTMX swap 대상."""
    tid = topic.id
    children = [H1(t("내 주제 관리", "Manage My Topic"))]
    if msg:
        # 화면에 떠서 슬라이드 인 + 자동 사라짐 — 스크롤 위치와 무관하게 눈에 띔
        children.append(Div(msg, cls="manage-toast", aria_live="polite"))
    edit_form = Form(
        account_field(topic.host_email),
        *topic_text_fields(topic),
        _image_edit_fields(topic),
        Button(t("저장", "Save"), type="submit"),
        hx_post=f"/manage/{tid}/edit", hx_encoding="multipart/form-data",
        hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
    )
    delete_form = Form(
        Button(t("주제 삭제", "Delete topic"), type="submit", cls="danger"),
        hx_post=f"/manage/{tid}/delete",
        hx_confirm=t("정말 삭제하시겠습니까?", "Delete this topic?"),
        hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
    )
    children += [
        Section(H2(t("주제 편집", "Edit Topic")), edit_form, cls="edit-section"),
        _schedule_status(session, topic),
        Section(H2(t("삭제", "Delete")), delete_form, cls="delete-section"),
    ]
    return Div(*children, id=PANEL_ID, cls="manage-panel")


def register(app) -> None:
    # '내 주제 수정' 탭은 폐지 — MY(/my)에서 신원으로 내 주제를 연다.
    @app.get("/manage")
    def manage_redirect():
        return RedirectResponse("/my", status_code=303)

    @app.get("/manage/{topic_id}")
    def manage(request, session, topic_id: int):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        with get_session() as db:
            topic = get_owned_topic(db, topic_id, identity)
            if not topic:
                return _not_owned()
            return layout(t("내 주제 관리", "Manage My Topic"),
                          _panel(db, topic))

    @app.post("/manage/{topic_id}/edit")
    async def manage_edit(request, session, topic_id: int, title: str,
                          host_name: str = "", description: str = "",
                          image_url: str = "", remove_image: str = "",
                          image_file: UploadFile = None):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        with get_session() as db:
            topic = get_owned_topic(db, topic_id, identity)
            if not topic:
                return _not_owned()
            title = (title or "").strip()
            if not title:
                return _panel(db, topic,
                              msg=notice(t("제목은 필수입니다.", "Title required."),
                                         kind="error"))

            # 이미지: 새 업로드 > 새 URL > 제거 > 유지 (upload > url > remove > keep)
            try:
                stored = await save_image(image_file)
                new_url = stored or normalize_image_url(image_url)
            except UploadError as exc:
                return _panel(db, topic, msg=notice(str(exc), kind="error"))
            old_url = topic.image_url
            if new_url:
                topic.image_url = new_url
                if old_url and old_url != new_url:
                    delete_local_image(old_url)
            elif remove_image:
                topic.image_url = None
                delete_local_image(old_url)

            topic.title = title
            topic.host_name = (host_name or "").strip()
            topic.description = (description or "").strip()
            topic.updated_at = utcnow()
            db.add(topic)
            db.commit()
            db.refresh(topic)
            return _panel(db, topic,
                          msg=notice(t("저장되었습니다.", "Saved."), kind="success"))

    @app.post("/manage/{topic_id}/delete")
    def manage_delete(request, session, topic_id: int):
        identity = resolve_identity(request, session)
        if not identity:
            return login_required_page()
        with get_session() as db:
            topic = get_owned_topic(db, topic_id, identity)
            if not topic:
                return _not_owned()
            # 스케줄 해제 후 소프트 삭제 (free slot, then soft-delete)
            entry = entry_for_topic(db, topic.id)
            if entry:
                db.delete(entry)
            topic.deleted_at = utcnow()
            topic.updated_at = utcnow()
            db.add(topic)
            db.commit()
        return Div(
            H1(t("삭제되었습니다", "Topic deleted")),
            notice(t("주제가 삭제되었습니다.", "Your topic has been deleted."),
                   kind="success"),
            A(t("내 주제", "My topics"), href="/my", cls="btn secondary"),
            id=PANEL_ID, cls="manage-panel",
        )


def _not_owned():
    return Div(
        notice(t("주제를 찾을 수 없거나 접근 권한이 없습니다.",
                 "Topic not found, or you don't have access."), kind="error"),
        id=PANEL_ID, cls="manage-panel",
    )
