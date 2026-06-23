# Open Space MVP - Final Product Requirements Document

## Project Name

Open Space MVP

---

## Product Vision

Open Space MVP is a lightweight conference discussion scheduling platform.

Participants propose discussion topics before the event and receive a private magic link.

Using the magic link, participants can:

- Edit their topic
- Delete or cancel their topic
- Register their topic into an available timetable slot
- Change or cancel timetable registration

Attendees can:

- Browse proposed topics
- View the final timetable
- View a display-board mode during the event

The platform intentionally avoids user accounts and conference login integration.

Ownership and permissions are handled entirely through email-based magic links.

---

# Product Principles

## Open by Default

Anyone can propose a topic.

No account creation is required.

---

## Ownership Through Magic Link

A topic owner controls their topic through a secure email link.

No login is required.

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
- Close slots with a custom label (e.g. 키노트, 휴식) — closed slots are not bookable
- Assign / unassign topics to slots
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

Participant submits:

- Email (required)
- Nickname (optional — shown as 익명/Anonymous if blank)
- Topic title
- Description
- Topic image (optional — file upload or image URL)

---

## Step 3

System:

- Creates topic
- Generates secure magic link
- Emails magic link

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

Home

### /topics

주제 목록 (Topic List)

### /topics/new

주제 등록 (Submit Topic)

### /schedule

타임테이블 (Timetable)

### /board

전광판 (Display Board) — full timetable as cards, no-scroll, optional `?date=` day selector

---

## Magic Link Pages

### /manage/{token}

내 주제 관리 (Manage My Topic)

Functions:

- Edit topic (incl. image: upload / URL / remove)
- Delete topic
- Register timetable
- Change timetable
- Cancel timetable registration

---

## Admin Pages

### /admin

관리자 (Admin)

### /admin/topics

Topic moderation + assign topics to slots + seed/clear demo data

### /admin/rooms

Room management

### /admin/timeslots

Timeslot management — bulk generate, close/relabel/reopen slots

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

---

## Rule 4

Admin scheduling is optional but available (admin can assign/move topics).

---

## Rule 5

A topic may remain unscheduled.

---

## Rule 6

A closed slot (custom label, e.g. 키노트/휴식) accepts no topic.

---

# Data Model

## Topic

text id title description host_name(nickname, optional) host_email image_url edit_token_hash edit_token_expires_at status is_hidden created_at updated_at deleted_at

---

## Room

text id name sort_order created_at updated_at

---

## Timeslot

text id starts_at ends_at sort_order is_closed label created_at updated_at

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

Resend

Purpose:

- Magic link delivery

---

## Authentication

No login.

No OAuth.

No accounts.

Only:

text Magic Link Authentication

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

All user-facing text must use:

text Korean (English)

format.

Examples:

text 주제 등록 (Submit Topic) 주제 목록 (Topic List) 타임테이블 (Timetable) 전광판 (Display Board) 관리자 (Admin)

No language switcher required.

No i18n framework required.

---

# Security Requirements

## Magic Links

- Cryptographically secure token
- Store hash only
- Never store raw token

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

Admin area protected by:

text ADMIN_PASSWORD

stored in environment variables.

MVP does not require user management.

---

# Environment Variables

text DATABASE_URL RESEND_API_KEY BASE_URL ADMIN_PASSWORD MAIL_FROM SESSION_SECRET UPLOAD_DIR

See README.md for defaults and dev/prod deployment.

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

- Auto refresh every 45 seconds (date selection persists across refresh)
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

- Login
- User accounts
- OAuth
- PyCon integration
- Likes
- Comments
- Session attendance tracking
- Speaker profiles
- Realtime chat
- Notifications beyond magic-link email
- GraphQL
- Microservices
- React
- Next.js
- Vue
- Angular

---

# MVP Completion Checklist

- [x] Topic submission works (email/nickname/title/description/image)
- [x] Magic link email works (Resend + console fallback)
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
- [x] No login required
- [x] Entire flow works end-to-end (20+ passing tests)

Success is achieved when a participant can submit a topic, receive a magic link, schedule the topic, and see it appear on the public timetable without creating an account.

> Note: the original PRD listed "File uploads" as a non-goal; topic cover-image
> upload was later added by the owner's request (file upload + image URL).
