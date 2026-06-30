# Open Space MVP - Final Product Requirements Document

## Project Name

Open Space MVP

---

## Product Vision

Open Space MVP is a lightweight conference discussion scheduling platform.

Participants log in with their PyCon identity and propose discussion topics before the event.

As the verified owner (PyCon member id) of a topic, participants can:

- Edit their topic
- Delete or cancel their topic
- Register their topic into an available timetable slot
- Change or cancel timetable registration

Attendees can:

- Browse proposed topics
- View the final timetable
- View a display-board mode during the event

The platform intentionally avoids its own user accounts and passwords.

Ownership and permissions are handled through the PyCon member id, verified
server-side from the existing PyCon login.

---

# Product Principles

## Open by Default

Anyone can propose a topic.

No account creation is required.

---

## Ownership Through PyCon Identity

A topic owner is the PyCon account (member id) that created the topic.

Ownership is verified server-side from the PyCon session — no magic link, no email.

---

## Self-Service Scheduling

Topic owners choose their own timetable slot.

Administrators may also assign or move a topic into a slot (implemented).

---

## Minimal Administration

Administrators only:

- Create rooms
- Create time slots
- Moderate topics

---

## Simple Technology

The entire application should be maintainable by a single developer.

Avoid unnecessary complexity.

---

# User Types

## Participant

Can:

- Submit topics
- Manage own topics
- Register topics into timetable

Cannot:

- Manage other topics
- Access admin functions

---

## Attendee

Can:

- Browse topics
- View timetable
- View display board

Cannot:

- Modify data

---

## Administrator

Can:

- Create rooms
- Create time slots (bulk generator: date / start / length / break / count)
- Lay out the whole grid in the Timetable Builder (add/edit/delete rows & columns inline)
- Close slots with a custom label (e.g. 키노트, 휴식) — closed slots are not bookable
- Assign / unassign topics to slots
- Register display-board QR codes (2 slots: image + caption)
- Hide topics
- Delete topics
- Seed or clear demo data (one click)

---

# Core User Flow

## Step 1

Participant opens:

text 주제 등록 (Submit Topic)

---

## Step 2

Participant submits (email/host_pycon_id come from the verified identity):

- Nickname (optional — shown as 익명/Anonymous if blank)
- Topic title
- Description
- Topic image (optional — file upload or image URL)

---

## Step 3

System:

- Creates topic owned by the participant's PyCon member id

---

## Step 4

Participant opens:

text 내 주제 관리 (Manage My Topic)

---

## Step 5

Participant edits topic if needed.

---

## Step 6

Participant selects an available timetable slot.

---

## Step 7

Topic appears on:

text 타임테이블 (Timetable)

---

## Step 8

Attendees view:

text 전광판 (Display Board)

during the event.

---

# Pages

## Public Pages

### /

Home — 주제 등록 (Submit Topic) form. **Requires identity** (soft login). This is
the first screen after login. Email and host_pycon_id come from the verified
identity (not a form field); the participant fills nickname/title/description/image
only. No identity → a "PyCon 로그인 필요" page.

### /my

MY — 내 주제 대시보드 (My-topics dashboard). **Requires identity**. Lists the
signed-in participant's own topics (keyed by PyCon member id; one person can have
several), each linking to `/manage/{topic_id}`.

### /topics

주제 목록 (Topic List) — public sticker wall.

### /topics/new

Legacy path — **redirects to `/`** (the home is now the submit form). `POST
/topics/new` still creates the topic (identity-gated).

### /logout

`POST /logout` clears the local identity session. `GET /auth/check` is a JSON probe
(`{"authed": bool}`) used by the login gate to detect when a new-window PyCon login
has completed.

### /schedule

타임테이블 (Timetable) — public read-only. With `?topic={id}` (an owned topic) it
becomes **interactive for that topic** (owner-only): click an open cell to register/
move (POST `/schedule/{topic_id}/take`), cancel via `/schedule/{topic_id}/cancel`.
The 2-day scheduling window applies (see Timetable Rule 3).

### /schedule/own

HTMX partial (identity-gated) — returns the owner scheduling area for a selected
owned topic (`?topic={id}`); used when switching topics via chips on the timetable.

### /board

전광판 (Display Board) — full timetable as cards, no-scroll, optional `?date=` day
selector. The page shell loads once and self-polls `GET /board/live` every 45s
(HTMX `outerHTML` swap — flicker-free, replaces the old meta-refresh).

---

## Owner Pages (identity)

### /manage/{topic_id}

내 주제 관리 (Manage My Topic) — owner-only (identity == host_pycon_id, verified
server-side). Old `/manage` redirects to `/my`.

Functions:

- Edit topic (nickname/title/description, incl. image: upload / URL / remove) via
  `/manage/{topic_id}/edit`
- Delete topic via `/manage/{topic_id}/delete`
- Shows the current timetable assignment + a "타임테이블에서 자리 잡기" link to
  `/schedule?topic={topic_id}` (scheduling itself happens on the timetable view, not here)

---

## Admin Pages

### /admin

관리자 (Admin)

### /admin/topics

Topic moderation + assign topics to slots + seed/clear demo data

### /admin/timetable

타임테이블 짜기 (Timetable Builder) — a word-processor-style grid editor. Add times
(rows) downward and rooms (columns) sideways with ＋, edit a slot's time / room name
inline by clicking the cell, delete with ✕. A complement to the separate rooms /
timeslots pages for quickly laying out the whole grid.

### /admin/rooms

Room management

### /admin/timeslots

Timeslot management — bulk generate, close/relabel/reopen slots

### /admin/board

전광판 QR (Board QR) — register the QR codes (2 slots) shown at the bottom of the
display board (image upload / URL + caption — e.g. event info, survey link).

---

# Timetable Rules

## Rule 1

One topic can occupy:

text 0 or 1 slot

---

## Rule 2

One slot can contain:

text 0 or 1 topic

---

## Rule 3

Topic owners schedule their own topics.

Self-scheduling opens **2 days before the event start** (= the earliest timeslot's
date). Before that window, participant slot registration/moves are blocked and the
manage timetable is shown read-only with an "opens on" notice. (See
`is_scheduling_open` / `scheduling_opens_on` in `app/queries.py`,
`SCHEDULING_LEAD_DAYS = 2`.)

---

## Rule 4

Admin scheduling is optional but available (admin can assign/move topics) — and is
**not** restricted by the 2-day window; admins may assign anytime.

---

## Rule 5

A topic may remain unscheduled.

---

## Rule 6

A closed slot (custom label, e.g. 키노트/휴식) accepts no topic.

---

# Data Model

## Topic

text id title description host_name(nickname, optional) host_email host_pycon_id(owner key) host_username image_url status is_hidden created_at updated_at deleted_at

`host_pycon_id` (PyCon member id) is the stable ownership key; `host_email` is for
contact/display only (may change). Adding this column to an existing
SQLite DB needs a fresh DB or manual `ALTER TABLE` (create_all won't alter).

---

## Room

text id name sort_order created_at updated_at

---

## Timeslot

text id starts_at ends_at sort_order is_closed label created_at updated_at

---

## BoardQR

text id slot(1|2) image_url caption created_at updated_at

Display-board QR codes — one row per slot (`unique(slot)`). Rendered as a QR strip
at the bottom of `/board` (event info, survey, sponsor links, …).

---

## ScheduleEntry

text id topic_id room_id timeslot_id created_at updated_at

Constraints:

text unique(topic_id) unique(room_id, timeslot_id)

---

# Backend Stack

## Language

Python 3.12+ (managed with `uv`)

---

## Framework

FastHTML (Starlette-based) — used standalone for both routing and rendering.
(The original PRD listed FastAPI; the implementation uses FastHTML alone, no FastAPI.)

---

## ORM

SQLModel

---

## Database

SQLite

Future migration target:

text PostgreSQL

---

## Email Provider

None (removed).

Ownership is established via PyCon identity (server-verified member id); no email is sent.

---

## Authentication

No accounts in this app; no passwords stored. Identity & ownership:

1. **PyCon identity (soft login)** — server verifies the PyCon session cookie
   server-to-server (only works on a pycon.kr subdomain) and uses the member id as
   the ownership key. Required to submit/manage topics. `DEV_LOGIN_ENABLED` provides
   a manual dev bypass. (See `app/auth.py`.)
2. **Ownership** is by PyCon member id (`host_pycon_id`), verified server-side on
   each owner action. No tokens, no email — there is nothing bearer to leak.

No OAuth integration, no PyCon account creation here — identity is read from the
existing PyCon login.

---

# Frontend Stack

## Rendering

Server-side rendering

---

## Framework

FastHTML

Preferred.

Alternative:

text Jinja2 + HTMX

---

## Dynamic UI

HTMX

Used for:

- Topic updates
- Schedule registration
- Admin actions

---

## Styling

Implemented: a retro neon-sign theme (`static/app.css`) using the owner-supplied
palette, with `Press Start 2P` (Latin pixel) + `Galmuri` (Korean pixel) fonts loaded via CDN.

Markup keeps semantic HTML + meaningful CSS class hooks + responsive structure,
so the stylesheet can be swapped wholesale without touching templates.

---

# Language Requirements

The product supports **Korean and English**, switchable via a header toggle
(`KO | EN`). The selected language is stored in a `lang` cookie and applied to
every page. (Default: Korean.)

Implementation (supersedes the original "no switcher / `Korean (English)` only"
note — the owner requested a real toggle):

- A tiny `t(ko, en)` helper in `app/i18n.py` returns one language at render time.
  Korean and English live side-by-side at each call site, e.g.
  `t("주제 등록", "Submit Topic")` — no separate message catalog, no i18n framework.
- The request language is set per-request by a pure ASGI middleware
  (`LangMiddleware` in `app/main.py`) that reads the `lang` cookie into a
  `contextvar`. A plain ASGI middleware is required (not FastHTML `before` /
  Starlette `BaseHTTPMiddleware`) so the contextvar propagates into sync route
  handlers that Starlette runs in a threadpool.
- The `/lang/{code}` route sets the cookie and redirects back (local paths only —
  open-redirect guarded).
- Inline JS strings, `hx_confirm`, and `confirm()` dialogs are localized by
  injecting `t(...)` values at render time (see `_live_preview_js()`,
  `pycon_prefill_js()` etc.).

Code comments and docstrings stay in the original `한글 (English)` bilingual form
(developer-facing — not user-facing, not localized).

---

# Security Requirements

## Ownership

- Owner = PyCon member id (`host_pycon_id`)
- Verified server-side from the PyCon session on each owner action
- No bearer tokens to leak (no magic links, no edit tokens)

---

## Email Privacy

Never expose:

text host_email

publicly.

---

## Scheduling Integrity

Database constraints must prevent:

- Double booking
- Duplicate scheduling

---

## Admin Protection

Admin access is by **identity email allowlist** — no password. A logged-in user
whose PyCon email is in `ADMIN_EMAILS` (comma-separated env var) is an admin: the
"관리자 (Admin)" nav tab appears and all `/admin/*` routes are unlocked. Non-admins
(or anonymous) are redirected to `/`. (See `is_admin_email` in `app/auth.py`,
`_require_admin` in `app/routes/admin.py`. No `/admin/login`; admin uses the same
PyCon identity / dev login as everyone else.)

MVP does not require user management.

---

# Environment Variables

text DATABASE_URL BASE_URL ADMIN_EMAILS SESSION_SECRET UPLOAD_DIR DEV_LOGIN_ENABLED

`ADMIN_EMAILS` — comma-separated admin emails (case-insensitive); logging in with
one grants admin. `DEV_LOGIN_ENABLED=1` enables `POST /dev/login` (manual identity for local dev/tests);
leave unset in production (pycon.kr) where identity comes from server-verified PyCon

`DEV_LOGIN_ENABLED=1` enables `POST /dev/login` (manual identity for local dev/tests);
leave unset in production (pycon.kr) where identity comes from server-verified PyCon
sessions. See README.md for defaults and dev/prod deployment.

---

# Deployment

## Container

Docker

---

## Requirements

- Single container deployment
- SQLite persistent volume
- Environment variables

---

# Board Requirements

Display board (`/board`, `/board?date=YYYY-MM-DD`):

- Auto refresh every 45 seconds via HTMX self-polling of `/board/live` (flicker-free
  `outerHTML` swap; date selection persists across refresh)
- QR strip at the bottom (admin-registered BoardQR codes, up to 2)
- Show the WHOLE timetable as cards, grouped by timeslot
- Show empty slots too (비어있음/open) so attendees see open times
- Closed slots shown as labeled cards (키노트, 휴식, …)
- Fit everything on one screen — NO scrolling (rows auto-size to viewport)
- Date selector tabs when the event spans multiple days
- Topic image shown as card background; full titles visible
- Large typography, projector friendly

---

# Accessibility

Use semantic HTML:

html main header section article nav table form button

All form controls must have labels.

Keyboard navigation must work.

---

# Non Goals

Do NOT implement:

- Our own login / passwords (identity is read from the existing PyCon session — no app accounts)
- User accounts (no account creation in this app)
- OAuth
- PyCon feature integration beyond the read-only server-side session check (no PyCon write APIs, no profile sync)
- Likes
- Comments
- Session attendance tracking
- Speaker profiles
- Realtime chat
- Email or any out-of-band notifications
- GraphQL
- Microservices
- React
- Next.js
- Vue
- Angular

---

# MVP Completion Checklist

- [x] Topic submission works (email/nickname/title/description/image)
- [x] PyCon identity (server-verified) + soft login works
- [x] Topic editing works (incl. image replace/remove)
- [x] Topic deletion works
- [x] Room management works
- [x] Timeslot management works (bulk generate)
- [x] Slot close/relabel/reopen works
- [x] Timetable registration works
- [x] Timetable changes work
- [x] Timetable cancellation works
- [x] Admin can assign topics to slots
- [x] Public topic list works (sticker wall)
- [x] Public timetable works
- [x] Display board works (no-scroll, all slots, date selector)
- [x] Admin moderation works
- [x] Demo data seeding works
- [x] Mobile layout works
- [x] Docker deployment configured
- [x] No app accounts/passwords (identity from PyCon login)
- [x] Entire flow works end-to-end (20+ passing tests)

Success is achieved when a participant can log in with their PyCon identity, submit a topic, schedule the topic, and see it appear on the public timetable without creating a separate account.

> Note: the original PRD listed "File uploads" as a non-goal; topic cover-image
> upload was later added by the owner's request (file upload + image URL).
