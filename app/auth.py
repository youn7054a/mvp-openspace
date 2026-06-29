"""PyCon 신원 (Identity) — 서버 측 세션 검증 + dev 우회.

신뢰 모델: 앱을 pycon.kr 서브도메인에 올리면 PyCon 세션 쿠키(Domain=pycon.kr)가
우리 서버 요청에도 함께 실려온다. 그 쿠키를 PyCon 세션 API로 서버-투-서버로 전달해
이메일·회원 id 를 검증한다(브라우저 JS 가 아니라 서버가 검증 → CORS 무관, 위변조 불가).
개발/타 도메인에선 쿠키가 없으므로 DEV_LOGIN_ENABLED + /dev/login 으로 우회한다.

소유권 키는 PyCon 회원 id(pycon_id) — 이메일은 바뀔 수 있어 연락·표시용으로만 쓴다.
"""
from __future__ import annotations

import contextvars
import logging
from dataclasses import asdict, dataclass

import httpx

from .config import get_settings

logger = logging.getLogger("openspace.auth")

# 현재 요청의 신원 (per-request identity) — nav의 관리자 탭 노출 판단 등에 사용.
_identity_var: contextvars.ContextVar = contextvars.ContextVar(
    "identity", default=None)

# PyCon 세션/로그인 엔드포인트 (Shared PyCon endpoints).
PYCON_SESSION_URL = (
    "https://rest-api.pycon.kr/authn/social/browser/v1/auth/session"
)
PYCON_SIGNIN_URL = "https://2026.pycon.kr/account/sign-in"

# 세션에 신원을 보관하는 키 (Identity cached in our signed session).
_SESSION_KEY = "identity"


@dataclass
class Identity:
    """검증된 PyCon 신원 (Verified identity)."""

    pycon_id: int
    email: str
    username: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Identity | None":
        if not d:
            return None
        try:
            return cls(
                pycon_id=int(d["pycon_id"]),
                email=str(d.get("email", "")),
                username=str(d.get("username", "")),
            )
        except (KeyError, TypeError, ValueError):
            return None


def set_identity(session, identity: Identity) -> None:
    """우리 세션에 신원 저장 (cache identity in session)."""
    session[_SESSION_KEY] = asdict(identity)


def clear_identity(session) -> None:
    session.pop(_SESSION_KEY, None)


def current_identity() -> Identity | None:
    """이번 요청에서 확인된 신원 (contextvar) — 렌더(nav 등)에서 사용."""
    return _identity_var.get()


def note_identity(identity: Identity | None) -> None:
    """렌더용 신원 contextvar 세팅 (resolve 없이 세션값을 쓸 때)."""
    _identity_var.set(identity)


def identity_from_session(session) -> Identity | None:
    """세션에 캐시된 신원 (no PyCon call) — 캐시만 읽는다."""
    return Identity.from_dict(session.get(_SESSION_KEY))


def is_admin_email(identity: Identity | None) -> bool:
    """이 신원이 관리자인가 — 이메일이 ADMIN_EMAILS 목록에 있으면 True."""
    if not identity or not identity.email:
        return False
    return identity.email.strip().lower() in get_settings().admin_emails


def _verify_with_pycon(request) -> Identity | None:
    """요청 쿠키를 PyCon 세션 API로 전달해 신원을 서버 검증한다.

    pycon.kr 서브도메인에 배포됐을 때만 쿠키가 실려와 동작한다. 그 외(로컬/타 도메인)
    에선 쿠키가 없어 미인증으로 떨어진다(막지 않음 — 호출부에서 게이트 처리).
    """
    # 개발 모드에선 신원이 /dev/login 으로만 들어오므로 PyCon 호출을 하지 않는다
    # (안 그러면 로컬 익명 요청마다 rest-api.pycon.kr 로 5초짜리 호출이 나감).
    if get_settings().dev_login_enabled:
        return None
    cookie = request.headers.get("cookie")
    if not cookie:
        return None
    try:
        resp = httpx.get(
            PYCON_SESSION_URL,
            headers={"cookie": cookie, "accept": "application/json"},
            timeout=4.0,
        )
        data = resp.json()
    except Exception:  # pragma: no cover - 네트워크/파싱 실패 시 막지 않음
        logger.debug("PyCon 세션 검증 실패 (treated as anonymous).", exc_info=True)
        return None

    meta = data.get("meta") or {}
    user = (data.get("data") or {}).get("user") or {}
    if not meta.get("is_authenticated") or not user.get("id"):
        return None
    try:
        pycon_id = int(user["id"])
    except (TypeError, ValueError):  # 비정상 id → 익명 처리(500 방지)
        return None
    return Identity(
        pycon_id=pycon_id,
        email=str(user.get("email", "")),
        username=str(user.get("username", "")),
    )


def resolve_identity(request, session) -> Identity | None:
    """현재 요청의 신원 (Resolve identity) — 세션 캐시 → PyCon 서버 검증 순.

    한 번 확립되면 세션에 캐시해 매 요청 PyCon 을 호출하지 않는다.
    """
    cached = Identity.from_dict(session.get(_SESSION_KEY))
    if cached:
        _identity_var.set(cached)
        return cached
    identity = _verify_with_pycon(request)
    if identity:
        set_identity(session, identity)
    _identity_var.set(identity)
    return identity


# 새 창에서 PyCon 로그인 → 서버검증(/auth/check) 폴링 → 로그인되면 자동 새로고침.
# (pycon.kr 서브도메인 배포에서만 동작 — 로그인 시 .pycon.kr 쿠키가 서버로 옴.)
_LOGIN_GATE_JS = """
(function () {
  var btn = document.getElementById('pycon-login-btn');
  var note = document.getElementById('pycon-login-note');
  if (!btn) return;
  var win = null, poll = null;
  function check() {
    fetch('/auth/check', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        if (b && b.authed) {
          if (poll) { clearInterval(poll); poll = null; }
          if (win) { try { win.close(); } catch (e) {} }
          location.reload();
        }
      })
      .catch(function () {});
  }
  btn.addEventListener('click', function () {
    win = window.open('%s', 'pycon-login', 'width=520,height=720');
    if (note) note.hidden = false;
    if (!poll) poll = setInterval(check, 3000);
  });
})();
"""


def login_required_page():
    """신원이 없을 때 보여줄 '로그인 필요' 화면 (soft-login gate page).

    'PyCon 로그인' 버튼은 새 창에서 로그인을 띄우고, 로그인이 끝나면(=서버가
    .pycon.kr 세션을 검증 가능해지면) 이 페이지가 자동으로 새로고침된다.
    """
    from fasthtml.common import H1, Button, Div, Script

    from .components import layout, notice
    from .i18n import t

    children = [
        H1(t("로그인이 필요합니다", "Login required")),
        notice(t("주제를 등록하거나 관리하려면 PyCon 로그인이 필요합니다.",
                 "Please log in with PyCon to submit or manage topics."),
               kind="info"),
        Button(t("PyCon 로그인 (새 창)", "Log in with PyCon (new window)"),
               type="button", id="pycon-login-btn", cls="btn"),
        notice(t("새 창에서 로그인하면 이 페이지가 자동으로 이어집니다…",
                 "Log in via the new window — this page continues automatically…"),
               kind="info"),
    ]
    # 위 안내는 클릭 전엔 숨김
    children[-1] = Div(children[-1], id="pycon-login-note", hidden=True)
    children.append(Script(_LOGIN_GATE_JS % PYCON_SIGNIN_URL))
    if get_settings().dev_login_enabled:
        from fasthtml.common import Form, Input, Label

        children.append(Form(
            Label(t("개발 로그인 이메일", "Dev login email"), fr="dev-email"),
            Input(id="dev-email", name="email", type="email", required=True,
                  placeholder="you@example.com"),
            # pycon_id 는 비우면 이메일에서 안정적으로 생성(이메일별 고유 소유자).
            Button(t("개발 로그인", "Dev login"), type="submit", cls="btn secondary"),
            method="post", action="/dev/login", cls="dev-login-form",
        ))
    return layout(t("로그인", "Login"), *children)
