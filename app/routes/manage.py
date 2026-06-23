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
    Option,
    P,
    Section,
    Select,
    Small,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from starlette.datastructures import UploadFile

from ..components import field, layout, notice
from ..database import get_session
from ..models import ScheduleEntry, Timeslot, Topic, utcnow
from ..queries import all_rooms, all_timeslots, entry_for_topic, schedule_map
from ..security import hash_token
from ..uploads import (
    UploadError,
    delete_local_image,
    normalize_image_url,
    save_image,
)

PANEL_ID = "manage-panel"


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


def _open_slot_options(session, *, include_current: ScheduleEntry | None = None):
    """예약 가능한 슬롯 옵션 (Open room×timeslot options)."""
    rooms = all_rooms(session)
    timeslots = all_timeslots(session)
    taken = schedule_map(session)
    options = []
    for ts in timeslots:
        if ts.is_closed:  # 닫힌 슬롯은 예약 불가 (closed slots not schedulable)
            continue
        for room in rooms:
            key = (room.id, ts.id)
            occupied = key in taken
            if occupied and not (
                include_current and taken[key].id == include_current.id
            ):
                continue
            options.append(
                Option(f"{room.name} · {ts.time_label}", value=f"{room.id}:{ts.id}")
            )
    return options


def _schedule_section(session, topic: Topic):
    """타임테이블 등록/변경/취소 UI."""
    entry = entry_for_topic(session, topic.id)
    if entry:
        room = next((r for r in all_rooms(session) if r.id == entry.room_id), None)
        ts = session.get(Timeslot, entry.timeslot_id)
        current_label = (
            f"{room.name if room else '?'} · {ts.time_label if ts else '?'}"
        )
        options = _open_slot_options(session, include_current=entry)
        change_form = Form(
            Select(*options, name="slot", aria_label="새 슬롯 (New slot)"),
            Button("슬롯 변경 (Change slot)", type="submit", cls="secondary"),
            hx_post=f"/manage/{_tok(topic)}/schedule",
            hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
        ) if options else P("변경 가능한 빈 슬롯이 없습니다. (No other open slots.)")
        cancel_form = Form(
            Button("등록 취소 (Cancel registration)", type="submit", cls="danger"),
            hx_post=f"/manage/{_tok(topic)}/unschedule",
            hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
        )
        return Section(
            H2("타임테이블 (Timetable)"),
            notice(f"현재 배정 (Scheduled): {current_label}", kind="success"),
            change_form,
            cancel_form,
            cls="schedule-section",
        )

    options = _open_slot_options(session)
    if not options:
        register = notice(
            "예약 가능한 슬롯이 없습니다. 관리자에게 문의하세요. "
            "(No open slots — contact the admin.)"
        )
    else:
        register = Form(
            Select(*options, name="slot", aria_label="슬롯 선택 (Choose a slot)"),
            Button("타임테이블 등록 (Register)", type="submit"),
            hx_post=f"/manage/{_tok(topic)}/schedule",
            hx_target=f"#{PANEL_ID}", hx_swap="outerHTML",
        )
    return Section(
        H2("타임테이블 (Timetable)"),
        P("아직 등록되지 않았습니다. 빈 슬롯을 선택하세요. (Not scheduled yet.)"),
        register,
        cls="schedule-section",
    )


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
        children.append(msg)
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
    @app.get("/manage/{token}")
    def manage(token: str):
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
            return layout("내 주제 관리 (Manage My Topic)", _panel(session, topic))

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
