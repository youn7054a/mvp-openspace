# 열린공간 (OpenSpace)

컨퍼런스 토론 주제 스케줄링 플랫폼 (A lightweight conference open-space scheduler).

앱 자체에는 계정·비밀번호가 없습니다. 신원은 **PyCon 로그인**에서 오고, 주제 소유권은
**PyCon 회원 id(서버 검증)** 로 확인합니다. 참가자가 직접 타임테이블 슬롯을 예약합니다.
(No accounts/passwords here — identity & ownership come from PyCon login, server-verified.)

## 기술 스택 (Stack)

- **FastHTML** (Starlette 기반) — 서버 렌더링 + HTMX
- **SQLModel + SQLite** — 데이터 (PostgreSQL 마이그레이션 대비)
- **PyCon 신원** — 세션 쿠키를 PyCon 세션 API로 서버-투-서버 검증 (이메일/계정 없음)
- **Python 3.12+**, `uv` 패키지 관리
- 디자인: 레트로 네온 — `Press Start 2P`(영문 픽셀) + `Galmuri`(한글 픽셀), CDN 로드

## 주요 기능 (Features)

- **홈 = 주제 등록 폼** (`/`) — 로그인 후 첫 화면. 별명(선택, 비우면 익명) · 제목 · 설명 · **대표 이미지(업로드 또는 URL)**, 입력에 따라 채워지는 카드 실시간 미리보기 (이메일/신원은 PyCon 신원에서 자동 공급)
- **MY = 내 주제 대시보드** (`/my`) — 내가 등록한 주제 목록(각 항목 → `/manage/{topic_id}`)
- **내 주제 관리** (`/manage/{topic_id}`) — 신원 소유 확인, 편집·삭제·이미지 교체/제거. 자리 잡기는 `/schedule?topic={topic_id}` 에서
- **자가 등록 윈도우** — 참가자 타임테이블 등록은 **행사 시작 이틀 전부터** 열림(그 전엔 보기 전용 + 안내). 관리자 배정은 예외(언제나 가능)
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
| `BASE_URL` | 외부 공개 주소 | `http://localhost:5001` |
| `ADMIN_EMAILS` | 관리자 이메일(쉼표로 여러 개). 이 이메일로 로그인하면 관리자 | (빈값) |
| `SESSION_SECRET` | 세션 쿠키 서명 키 | (개발용 기본값) |
| `UPLOAD_DIR` | 업로드 이미지 저장 디렉토리 | `./uploads` |
| `DEV_LOGIN_ENABLED` | **개발용 수기 로그인**(`/dev/login`) 허용 — 운영(pycon.kr)에선 미설정 | (빈값=꺼짐) |

## 페이지 (Pages)

| 경로 | 설명 |
|------|------|
| `/` | 홈 (Home) — **주제 등록 폼**(로그인 필요): 로그인 후 첫 화면 |
| `/my` | MY — **내 주제 대시보드**(로그인 필요): 내 주제 목록(각 항목 → `/manage/{id}`) |
| `/topics` | 주제 목록 (Topic List) — 스티커 벽 (공개) |
| `/topics/new` | → `/` 로 리다이렉트 (홈이 등록 폼) |
| `/manage/{topic_id}` | 내 주제 관리 — 신원 소유 확인, 편집/삭제/이미지. 일정은 타임테이블에서 |
| `/schedule` | 타임테이블 (Timetable) — 공개 읽기. `?topic={id}`이면 그 주제로 **자리 잡기** |
| `/board` · `/board?date=YYYY-MM-DD` | 전광판 (Display Board) |
| `/admin` | 관리자 — 주제 모더레이션·배정 / 룸 / 타임슬롯 / 데모 데이터 |

## 핵심 플로우 (Core flow)

1. PyCon 로그인 후 홈(`/`)에서 주제 제출
2. `/my`(MY)에서 내 주제 확인 → 항목의 `/manage/{topic_id}` 열어 편집
3. "타임테이블에서 자리 잡기" → `/schedule?topic={topic_id}` 에서 빈 슬롯 예약 (관리자도 `/admin/topics`에서 배정 가능)
4. `/schedule`·`/board` 에 자동 노출
5. 관리자(`/admin`)는 룸/타임슬롯 생성, 슬롯 닫기/라벨, 주제 숨김/삭제, 배정

스케줄 무결성은 DB 유니크 제약으로 보장됩니다
(`unique(topic_id)`, `unique(room_id, timeslot_id)`) — 더블부킹/중복 등록 차단.

보안: 소유권은 **PyCon 회원 id(서버 검증)** 로 확인하고, `host_email`은 공개 노출 안 함,
업로드는 무작위 파일명 + 형식(PNG/JPG/GIF/WEBP)·크기(5MB) 검증.

## PyCon 로그인(서버 검증) & 소프트 로그인 (PyCon identity & soft login)

신원 = **PyCon 회원 id**(안정적 소유권 키). 이메일은 연락·표시용이며 바뀔 수 있어 보조로만
씁니다. 주제 등록·내 주제 관리는 **신원이 있어야** 합니다(소프트 로그인). 신원이 없으면
"PyCon 로그인 필요" 페이지가 표시됩니다. 매직링크/토큰/이메일은 사용하지 않습니다.

**신뢰 모델 — 서버 검증.** 앱을 **`pycon.kr` 서브도메인**(예: `openspace.pycon.kr`)에 올리면
PyCon 세션 쿠키(`Domain=pycon.kr`)가 우리 서버 요청에도 함께 실려옵니다. 서버가 그 쿠키를
PyCon 세션 API(`rest-api.pycon.kr/.../auth/session`)로 **그대로 전달해 서버-투-서버로 검증**하고
`data.user.{id,email,username}` 를 신원으로 확립합니다(우리 세션 쿠키에 캐시). 브라우저 JS가 아니라
**서버가 검증**하므로 CORS 무관·위변조 불가입니다.

- **홈(`/`)**: 신원 필요. 주제 등록 폼이 첫 화면. `host_email`·`host_pycon_id` 는 **신원에서 자동 공급**(폼에 이메일 없음).
- **MY(`/my`)**: 신원으로 **내 주제 목록**(회원 id 기준). 항목 클릭 →
  `/manage/{topic_id}` 가 소유자(신원==host_pycon_id)를 재검증 후 진입.
- **일정**: 수정 화면의 "타임테이블에서 자리 잡기" → `/schedule?topic={topic_id}` 에서 빈 칸 클릭 등록/이동/취소
  (`POST /schedule/{topic_id}/take`·`/cancel`).

> 🔧 **개발/타 도메인.** pycon.kr 쿠키가 없으면 검증이 안 되므로, `DEV_LOGIN_ENABLED=1` 로
> `POST /dev/login {email}`(또는 로그인 화면의 개발 로그인 폼)을 켜서 신원을 흉내냅니다. 운영에선
> 이 변수를 **설정하지 마세요**.
>
> ⚠️ 운영 배포 도메인은 PyCon CORS/쿠키가 동작하도록 **`pycon.kr` 서브도메인**이어야 합니다
> (기본 Railway 도메인에선 세션 쿠키가 오지 않아 검증 불가 → 사실상 접근 불가).

## 테스트 (Tests)

```bash
uv run pytest
```

End-to-end 스모크 테스트(20+): 개발 로그인(신원) → 주제 제출 → 편집/이미지 → 예약 → 타임테이블 →
더블부킹 차단 → 슬롯 닫기/라벨 → 관리자 배정 → 전광판(일자 선택) → 데모 시드.

---

# 배포 (Deployment)

## 개발 (Development)

로컬에서 빠르게 돌려보는 모드. pycon.kr 쿠키가 없으므로 `DEV_LOGIN_ENABLED=1` 로 로컬 로그인을 켜고 전체 플로우 테스트.

```bash
# 1) 의존성 설치
uv sync

# 2) 환경 변수 (DEV_LOGIN_ENABLED=1 로 로컬 로그인 허용)
cp .env.example .env

# 3) 실행 (자동 리로드)
uv run uvicorn app.main:app --host 127.0.0.1 --port 5001 --reload
#    또는: uv run python -m app.main
```

- 접속: <http://localhost:5001>
- 관리자: `.env`의 `ADMIN_EMAILS`에 본인 이메일을 넣고 그 이메일로 (개발) 로그인 → nav에 **관리자** 탭 → **데모 데이터 채우기**
- 로그인: `DEV_LOGIN_ENABLED=1` 일 때 로그인 화면의 개발 로그인 폼(또는 `POST /dev/login`)으로 신원 흉내
- SQLite 파일 `./openspace.db`, 업로드 이미지 `./uploads/` (둘 다 `.gitignore` 처리)

## 운영 (Production)

단일 Docker 컨테이너 + 영속 볼륨. **`pycon.kr` 서브도메인 서빙 + 강한 비밀키**가 핵심.

```bash
# 1) 이미지 빌드
docker build -t openspace-mvp .

# 2) 환경 변수 파일 작성 (예: prod.env)
#    DATABASE_URL / UPLOAD_DIR 은 Dockerfile에서 /data 볼륨으로 기본 설정됨
cat > prod.env <<'ENV'
BASE_URL=https://openspace.pycon.kr               # 외부 공개 주소 (pycon.kr 서브도메인)
ADMIN_EMAILS=admin1@pycon.kr,admin2@pycon.kr   # 관리자 PyCon 이메일
SESSION_SECRET=<랜덤 32바이트 이상, openssl rand -hex 32>
ENV

# 3) 실행 (SQLite·업로드는 /data 볼륨에 영속)
docker run -d --name openspace -p 5001:5001 \
  --env-file prod.env \
  -v openspace-data:/data \
  --restart unless-stopped \
  openspace-mvp
```

## Railway 배포 (Railway)

Railway는 저장소의 **Dockerfile 을 자동 감지**해 빌드합니다(`railway.toml` 로 명시됨).
컨테이너는 Railway가 주입하는 **`$PORT`** 에 바인딩하도록 이미 설정돼 있어 추가 작업이 필요 없습니다.

**1) 프로젝트 생성**

- 대시보드에서 **New Project → Deploy from GitHub repo** → 이 저장소 선택
  (또는 CLI: `npm i -g @railway/cli && railway login && railway init && railway up`)
- 빌더는 `railway.toml` 의 `DOCKERFILE` 로 자동 설정됩니다.

**2) 영속 볼륨 연결 (필수)**

SQLite DB 와 업로드 이미지는 컨테이너의 `/data` 에 저장됩니다. 볼륨을 붙이지 않으면
**재배포·재시작 때마다 데이터가 사라집니다.**

- 서비스 → **Variables/Settings → Volumes → New Volume**
- **Mount path** 를 `/data` 로 지정
- 아래 `DATABASE_URL`·`UPLOAD_DIR` 를 이 마운트 경로에 맞춰 **반드시 설정**해야 데이터가 볼륨에 저장됩니다

**3) 환경 변수 설정**

서비스 → **Variables** 에 입력:

| 변수 | 값 |
| --- | --- |
| `BASE_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` ← 공개 도메인 참조 (외부 공개 주소) |
| `ADMIN_EMAILS` | 관리자 PyCon 이메일(쉼표로 여러 개) |
| `SESSION_SECRET` | `openssl rand -hex 32` 결과 |
| `DATABASE_URL` | `sqlite:////data/openspace.db` (볼륨 경로 — **슬래시 4개 = 절대경로**) |
| `UPLOAD_DIR` | `/data/uploads` (볼륨 경로) |

> ⚠️ `DATABASE_URL`·`UPLOAD_DIR` 는 **반드시 위 값으로 직접 설정**하세요. Dockerfile 의 해당
> `ENV` 라인은 주석 처리돼 있어, 설정하지 않으면 기본값(`./openspace.db`, `./uploads`)으로
> 컨테이너 내부에 저장돼 **재배포마다 데이터가 초기화**됩니다.
> - SQLite **절대경로는 슬래시 4개**: `sqlite:////data/...` (3개는 상대경로로 해석됨).
> - `.env` 는 로컬 전용(gitignore)이라 Railway 가 읽지 않습니다 — 모든 변수는 여기 **Variables** 에 넣으세요.

**4) 공개 도메인 생성 & 접속**

- 서비스 → **Settings → Networking → Generate Domain** 으로 공개 URL 발급
- `BASE_URL` 을 그 도메인으로 두면 외부 공개 주소가 올바르게 설정됩니다
  (위 `${{RAILWAY_PUBLIC_DOMAIN}}` 참조를 쓰면 자동)
- 배포 후 `/admin` 로그인 → (선택) **데모 데이터 채우기** 로 동작 확인

> ⚠️ Railway 볼륨은 **단일 인스턴스** 기준입니다. SQLite는 단일 라이터라 잘 맞지만,
> 수평 확장(레플리카)이 필요해지면 PostgreSQL 로 옮기세요(`DATABASE_URL` 만 교체).
> TLS·HTTPS 는 Railway 도메인에서 자동 처리됩니다.

> 🔑 **PyCon 로그인 연동을 쓰는 경우**: PyCon 세션 API는 CORS 로 **`*.pycon.kr` origin 만 허용**합니다.
> 기본 Railway 도메인(`*.up.railway.app`)에서는 로그인 확인이 CORS 로 차단되니, 앱을
> **`pycon.kr` 서브도메인**(예: `openspace.pycon.kr`)으로 서빙하세요 — Railway 커스텀 도메인 추가 +
> PyCon DNS(CNAME) 연결. 그러면 코드 변경 없이 CORS 가 풀리고, 로그인 쿠키(`Domain=pycon.kr`)가
> 공유돼 로그인 확인도 동작합니다. `BASE_URL` 도 그 주소로 설정하세요.

운영 체크리스트:

- [ ] **`ADMIN_EMAILS`** 에 실제 관리자 PyCon 이메일 설정, **`SESSION_SECRET`** 강한 랜덤값으로 교체
- [ ] **`BASE_URL`** 을 실제 공개 주소(`pycon.kr` 서브도메인)로 설정
- [ ] **TLS** — 리버스 프록시(Nginx/Caddy/클라우드 LB) 뒤에서 HTTPS 종단
- [ ] **볼륨 백업** — `/data` (SQLite DB + 업로드 이미지) 정기 백업
- [ ] 데이터가 늘면 PostgreSQL 로 마이그레이션 (`DATABASE_URL` 교체)

> 참고: 관리자 페이지의 **"데모 데이터 채우기/전체 비우기"** 는 기존 데이터를 교체/삭제하므로
> 운영 환경에서는 사용에 주의하세요.
