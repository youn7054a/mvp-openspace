#!/usr/bin/env python3
"""공개 OpenSpace 화면을 GitHub Pages용 정적 아카이브로 내보낸다.

운영 DB와 uploads 디렉터리가 있는 환경에서 실행한다. 신청·관리·로그인 화면은
명시적으로 제외하며, 공개 화면에서 실제 참조한 /uploads 파일만 복사한다.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


PAGES = {
    "/topics": "topics/index.html",
    "/programs": "programs/index.html",
    "/schedule": "schedule/index.html",
    "/board": "board/index.html",
    "/board2": "board2/index.html",
    "/board3": "board3/index.html",
    "/light/board": "light/board/index.html",
}

ARCHIVE_LINKS = {
    "/": "/",
    "/topics": "/topics/",
    "/programs": "/programs/",
    "/schedule": "/schedule/",
    "/board": "/board/",
    "/board2": "/board2/",
    "/board3": "/board3/",
    "/light/board": "/light/board/",
}

UPLOAD_URL_RE = re.compile(r"(?:src|href|url)=[\"']?(/uploads/[^\"'?#)\s]+)")
CSS_UPLOAD_URL_RE = re.compile(r"url\([\"']?(/uploads/[^\"'?#)\s]+)")
HTMX_ATTRIBUTE_RE = re.compile(r"\s+hx-[\w-]+=(?:\"[^\"]*\"|'[^']*')")


def _base_path(value: str) -> str:
    value = value.strip().strip("/")
    return f"/{value}" if value else ""


def _archive_url(url: str, base_path: str) -> str:
    """앱의 루트 절대 URL을 GitHub Pages 프로젝트 경로로 바꾼다."""
    parsed = urlsplit(url)
    if not parsed.path.startswith("/"):
        return url
    if parsed.path == "/board":
        selected_date = parse_qs(parsed.query).get("date", [""])[0]
        if selected_date:
            return f"{base_path}/board/{selected_date}/"
    target = ARCHIVE_LINKS.get(parsed.path, "/")
    return f"{base_path}{target}"


def _rewrite_html(html: str, base_path: str) -> str:
    """동적 요청·운영 링크를 제거하고 정적 사이트 경로로 변환한다."""
    html = re.sub(r'<script[^>]+src="https://unpkg\.com/htmx\.org[^>]*></script>', "", html)
    html = HTMX_ATTRIBUTE_RE.sub("", html)
    html = re.sub(r'<meta[^>]+http-equiv="refresh"[^>]*>', "", html, flags=re.IGNORECASE)

    def replace_url(match: re.Match[str]) -> str:
        attribute, quote, url = match.groups()
        if url.startswith("/static/") or url.startswith("/uploads/"):
            replacement = f"{base_path}{url}"
        else:
            replacement = _archive_url(url, base_path)
        return f"{attribute}={quote}{replacement}{quote}"

    return re.sub(r'(href|src)=("|\')(/[^"\']*)\2', replace_url, html)


def _referenced_uploads(html: str) -> set[str]:
    matches = set(UPLOAD_URL_RE.findall(html))
    matches.update(CSS_UPLOAD_URL_RE.findall(html))
    return matches


def _copy_uploads(urls: set[str], uploads_dir: Path, destination: Path) -> None:
    for url in urls:
        relative = Path(unquote(url.removeprefix("/uploads/")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe upload URL: {url}")
        source = uploads_dir / relative
        if not source.is_file():
            raise FileNotFoundError(f"Referenced upload is missing: {source}")
        target = destination / "uploads" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _write_index(destination: Path, base_path: str) -> None:
    links = "".join(
        f'<li><a href="{base_path}{path}">{label}</a></li>'
        for path, label in (
            ("/topics/", "주제 목록"),
            ("/schedule/", "타임테이블"),
            ("/programs/", "프로그램 소개"),
            ("/board/", "전광판"),
        )
    )
    (destination / "index.html").write_text(
        "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>열린공간 2026 아카이브</title>"
        f"<link rel=\"stylesheet\" href=\"{base_path}/static/app.css\"></head>"
        "<body><main class=\"content\"><h1>열린공간 2026 아카이브</h1>"
        "<p>행사 종료 시점의 공개 페이지를 보관한 읽기 전용 아카이브입니다.</p>"
        f"<ul>{links}</ul></main></body></html>",
        encoding="utf-8",
    )


def export_archive(output_dir: Path, base_path: str) -> None:
    # 환경 변수를 설정한 뒤 호출돼야 한다. 그래야 운영 DB의 공개 상태를 그대로 읽는다.
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from starlette.testclient import TestClient

    from app.database import get_session
    from app.main import create_app
    from app.queries import all_timeslots

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    uploads = Path(os.environ.get("UPLOAD_DIR", "./uploads")).resolve()
    static = Path("static").resolve()
    shutil.copytree(static, output_dir / "static")

    app = create_app()
    pages = dict(PAGES)
    with get_session() as session:
        board_dates = sorted({item.starts_at.date().isoformat()
                              for item in all_timeslots(session)})
    for day in board_dates:
        pages[f"/board?date={day}"] = f"board/{day}/index.html"
    uploads_to_copy: set[str] = set()
    with TestClient(app) as client:
        for path, relative_output in pages.items():
            response = client.get(path)
            response.raise_for_status()
            html = response.text
            uploads_to_copy.update(_referenced_uploads(html))
            target = output_dir / relative_output
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_rewrite_html(html, base_path), encoding="utf-8")

    _copy_uploads(uploads_to_copy, uploads, output_dir)
    _write_index(output_dir, base_path)
    (output_dir / ".nojekyll").touch()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the public OpenSpace static archive.")
    parser.add_argument("--output", type=Path, default=Path("archive/site"))
    parser.add_argument("--database", type=Path, default=Path("openspace.db"))
    parser.add_argument("--uploads", type=Path, default=Path("uploads"))
    parser.add_argument("--base-path", default="/mvp-openspace",
                        help="GitHub Pages project path; use an empty value for a custom domain.")
    args = parser.parse_args()

    database = args.database.resolve()
    if not database.is_file():
        raise SystemExit(f"Database not found: {database}")
    os.environ["DATABASE_URL"] = f"sqlite:///{database}"
    os.environ["UPLOAD_DIR"] = str(args.uploads.resolve())
    export_archive(args.output.resolve(), _base_path(args.base_path))


if __name__ == "__main__":
    main()
