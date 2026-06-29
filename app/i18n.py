"""다국어 지원 (Internationalization) — 요청 스코프 언어 + t() 헬퍼.

언어는 요청마다 ``lang`` 쿠키로 결정되며, Beforeware(app/main.py)가 contextvar 에
값을 세팅한다. 라우트/컴포넌트는 ``t(ko, en)`` 만 호출하면 되고 lang 을 인자로
넘길 필요가 없다. Beforeware 는 라우트 핸들러와 같은 async 컨텍스트에서 실행되어
contextvar 전파가 안전하다.
"""
from __future__ import annotations

import contextvars

# 지원 언어 (Supported languages): 한국어 기본 + 영어
DEFAULT_LANG = "ko"

_lang: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default=DEFAULT_LANG)
# 헤더 언어 토글의 next 링크용 — 현재 요청 경로(+쿼리)
_path: contextvars.ContextVar[str] = contextvars.ContextVar("path", default="/")


def normalize_lang(code: str | None) -> str:
    """언어 코드 정규화 (Normalize) — 'en' 만 영어, 그 외 한국어."""
    return "en" if (code or "").lower() == "en" else "ko"


def set_lang(code: str | None) -> None:
    """현재 요청 언어 설정 (Set request language)."""
    _lang.set(normalize_lang(code))


def get_lang() -> str:
    """현재 요청 언어 (Current request language): 'ko' | 'en'."""
    return _lang.get()


def set_path(path: str) -> None:
    """현재 요청 경로 저장 (Store request path) — 토글 next 용."""
    _path.set(path or "/")


def get_path() -> str:
    """현재 요청 경로 (Current request path)."""
    return _path.get()


def t(ko: str, en: str) -> str:
    """언어에 맞는 문자열 선택 (Pick localized string)."""
    return en if get_lang() == "en" else ko
