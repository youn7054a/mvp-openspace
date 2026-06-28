# Open Space MVP

컨퍼런스 토론 주제 스케줄링 플랫폼 (A lightweight conference open-space scheduler).

계정/로그인 없이 **이메일 매직링크**로 주제 소유권을 관리하고, 참가자가 직접
타임테이블 슬롯을 예약합니다. (No accounts — ownership via email magic links.)

## 기술 스택 (Stack)

- **FastHTML** (Starlette 기반) — 서버 렌더링 + HTMX
- **SQLModel + SQLite** — 데이터 (PostgreSQL 마이그레이션 대비)
- **Resend** — 매직링크 이메일 (키 없으면 콘솔 폴백)
- **Python 3.12+**, `uv` 패키지 관리
- 디자인: 레트로 네온 — `Press Start 2P`(영문 픽셀) + `Galmuri`(한글 픽셀), CDN 로드

## 주요 기능 (Features)

- **주제 등록** — 이메일(필수) · 별명(선택, 비우면 익명) · 제목 · 설명 · **대표 이미지(업로드 또는 URL)**, 입력에 따라 채워지는 카드 실시간 미리보기
- **매직링크 관리** (`/manage/{token}`) — 주제 편집·삭제, 이미지 교체/제거, 슬롯 예약·변경·취소
- **주제 목록** — 핀으로 꽂힌 **스티커 카드 벽**, 배정/미배정 상태 칩
- **타임슬롯 일괄 생성** — 날짜·시작시각·길이·휴식·개수로 연속 슬롯 한 번에 (실시간 미리보기)
- **슬롯 닫기/라벨** — "키노트", "휴식" 등 커스텀 라벨로 슬롯을 닫아 예약 불가 처리
- **관리자 직접 배정** — 관리자가 주제를 슬롯에 배정/해제 (더블부킹 차단)
- **전광판** (`/board`) — 전체 타임테이블을 **한 화면(무스크롤)** 카드로, 빈 슬롯도 "비어있음"으로 노출, 사진 배경, **표시 일자 선택 탭**, 45초 자동 새로고침
- **데모 데이터 시드** — 관리자 버튼 한 번으로 룸·슬롯·주제·배정 일괄 생성

## 환경 변수 (Environment variables)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DATABASE_URL` | SQLite 경로 | `sqlite:///./openspace.db` |
| `RESEND_API_KEY` | Resend 키. **비우면 콘솔 폴백** | (빈값) |
| `BASE_URL` | 매직링크 생성용 외부 주소 | `http://localhost:5001` |
| `ADMIN_PASSWORD` | 관리자 페이지 비밀번호 | `change-me` |
| `MAIL_FROM` | 발신 주소 (Resend 사용 시) | `onboarding@resend.dev` |
| `SESSION_SECRET` | 세션 쿠키 서명 키 | (개발용 기본값) |
| `UPLOAD_DIR` | 업로드 이미지 저장 디렉토리 | `./uploads` |

## 페이지 (Pages)

| 경로 | 설명 |
|------|------|
| `/` | 홈 (Home) |
| `/topics` | 주제 목록 (Topic List) — 스티커 벽 |
| `/topics/new` | 주제 등록 (Submit Topic) |
| `/manage/{token}` | 내 주제 관리 — 편집/삭제/이미지/예약 (magic link) |
| `/schedule` | 타임테이블 (Timetable) |
| `/board` · `/board?date=YYYY-MM-DD` | 전광판 (Display Board) |
| `/admin` | 관리자 — 주제 모더레이션·배정 / 룸 / 타임슬롯 / 데모 데이터 |

## 핵심 플로우 (Core flow)

1. 참가자가 `/topics/new` 에서 주제 제출 → 매직링크 이메일 수신 (개발 모드는 콘솔 출력)
2. `/manage/{token}` 에서 주제 편집 및 빈 슬롯 예약 (관리자도 `/admin/topics`에서 배정 가능)
3. `/schedule`·`/board` 에 자동 노출
4. 관리자(`/admin`)는 룸/타임슬롯 생성, 슬롯 닫기/라벨, 주제 숨김/삭제, 배정

스케줄 무결성은 DB 유니크 제약으로 보장됩니다
(`unique(topic_id)`, `unique(room_id, timeslot_id)`) — 더블부킹/중복 등록 차단.

보안: 매직링크 토큰은 **해시만 저장**(원본 미저장), `host_email`은 공개 노출 안 함,
업로드는 무작위 파일명 + 형식(PNG/JPG/GIF/WEBP)·크기(5MB) 검증.

## PyCon 로그인 연동 & 보안 한계 (PyCon login & trust model)

주제 등록(`/topics/new`)과 내 주제 수정(`/manage`)은 **PyCon 로그인**으로 게이트합니다.
브라우저가 PyCon 세션 API(`rest-api.pycon.kr/.../auth/session`)를 쿠키와 함께 호출해
로그인 여부·이메일을 확인하고, 로그인되어 있으면:

- `/topics/new`: 이메일 칸 자동 채움
- `/manage`: 이메일로 본인 주제를 찾아 관리 페이지로 **직접 진입**하고, 동시에
  **매직링크도 이메일로 발송**(다음엔 메일 링크로 바로 진입 가능)

> ⚠️ **신뢰 한계(주의).** PyCon 세션 쿠키는 `pycon.kr` 도메인에 있어 **서버가
> 로그인 신원을 직접 검증할 수 없습니다.** 이메일이 클라이언트에서 전달되므로,
> 악의적 사용자가 타인의 이메일을 주장하면 그 주제에 접근할 수 있는 위험이
> 있습니다(주제 등록 게이트와 동일한 "클라이언트 측 신뢰" 수준).
> 토픽 내용은 민감도가 낮아 현재는 이 편의 흐름을 허용합니다.
>
> **권장(운영 강화 시):**
> 1. 직접 진입 대신 **매직링크 재발송만** 제공 — 실제 메일 소유자만 진입.
> 2. PyCon이 검증 가능한 **OIDC/JWT 토큰**을 제공하면 서버에서 신원 검증 추가.
>
> 또한 운영 배포 도메인은 PyCon CORS allowlist에 등록돼 있어야 세션 확인이 동작합니다.

## 테스트 (Tests)

```bash
uv run pytest
```

End-to-end 스모크 테스트(20+): 주제 제출 → 매직링크 → 편집/이미지 → 예약 → 타임테이블 →
더블부킹 차단 → 슬롯 닫기/라벨 → 관리자 배정 → 전광판(일자 선택) → 데모 시드.

---

# 배포 (Deployment)

## 개발 (Development)

로컬에서 빠르게 돌려보는 모드. **이메일 키가 없어도** 매직링크가 콘솔에 출력되어 전체 플로우 테스트 가능.

```bash
# 1) 의존성 설치
uv sync

# 2) 환경 변수 (RESEND_API_KEY 는 비워두면 콘솔 폴백)
cp .env.example .env

# 3) 실행 (자동 리로드)
uv run uvicorn app.main:app --host 127.0.0.1 --port 5001 --reload
#    또는: uv run python -m app.main
```

- 접속: <http://localhost:5001>
- 관리자: `/admin` → 비밀번호 `change-me`(기본) → **데모 데이터 채우기** 버튼으로 빠르게 채우기
- 매직링크는 **서버 콘솔/로그**에 출력됨 (이메일 미발송)
- SQLite 파일 `./openspace.db`, 업로드 이미지 `./uploads/` (둘 다 `.gitignore` 처리)

## 운영 (Production)

단일 Docker 컨테이너 + 영속 볼륨. **실제 이메일 발송 + 강한 비밀키**가 핵심.

```bash
# 1) 이미지 빌드
docker build -t openspace-mvp .

# 2) 환경 변수 파일 작성 (예: prod.env)
#    DATABASE_URL / UPLOAD_DIR 은 Dockerfile에서 /data 볼륨으로 기본 설정됨
cat > prod.env <<'ENV'
RESEND_API_KEY=re_xxxxxxxx          # 실제 Resend 키
MAIL_FROM=Open Space <noreply@yourdomain.com>   # 인증된 도메인 주소
BASE_URL=https://openspace.yourdomain.com         # 공개 URL (매직링크에 사용)
ADMIN_PASSWORD=<길고-랜덤한-비밀번호>
SESSION_SECRET=<랜덤 32바이트 이상, openssl rand -hex 32>
ENV

# 3) 실행 (SQLite·업로드는 /data 볼륨에 영속)
docker run -d --name openspace -p 5001:5001 \
  --env-file prod.env \
  -v openspace-data:/data \
  --restart unless-stopped \
  openspace-mvp
```

운영 체크리스트:

- [ ] **`ADMIN_PASSWORD`·`SESSION_SECRET`** 을 기본값에서 강한 랜덤값으로 교체
- [ ] **Resend 도메인 인증** 후 `MAIL_FROM` 을 인증 도메인 주소로 설정
      (미인증 `onboarding@resend.dev` 는 본인 계정 이메일로만 발송됨)
- [ ] **`BASE_URL`** 을 실제 공개 주소로 — 매직링크가 이 주소로 생성됨
- [ ] **TLS** — 리버스 프록시(Nginx/Caddy/클라우드 LB) 뒤에서 HTTPS 종단
- [ ] **볼륨 백업** — `/data` (SQLite DB + 업로드 이미지) 정기 백업
- [ ] 데이터가 늘면 PostgreSQL 로 마이그레이션 (`DATABASE_URL` 교체)

> 참고: 관리자 페이지의 **"데모 데이터 채우기/전체 비우기"** 는 기존 데이터를 교체/삭제하므로
> 운영 환경에서는 사용에 주의하세요.
