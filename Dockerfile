# Open Space MVP — 단일 컨테이너 배포 (Single-container deployment)
FROM python:3.12-slim

# uv 설치 (Install uv)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 의존성 먼저 설치 (Install deps first for layer caching)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

# 애플리케이션 소스 (App source)
COPY app ./app
COPY static ./static

# SQLite + 업로드 이미지 영속 볼륨 (Persistent volume for SQLite & uploads)
# railway 주섯
# RUN mkdir -p /data /data/uploads
# ENV DATABASE_URL=sqlite:////data/openspace.db
# ENV UPLOAD_DIR=/data/uploads
# VOLUME ["/data"]

EXPOSE 5001

# 컨테이너 실행 (Run) — 환경변수는 -e 또는 --env-file 로 주입.
# Railway 등 PaaS는 $PORT 를 주입하므로 그 값에 바인딩하고, 없으면 5001(로컬 기본).
# shell 폼 + exec 로 SIGTERM 이 uvicorn 까지 전달되게 한다(graceful shutdown).
CMD ["sh", "-c", "exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-5001}"]
