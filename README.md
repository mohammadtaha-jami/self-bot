# Telegram Opportunity Detection & Lead Intelligence

<p align="center">
  <img src="docs/banner.png" alt="Project banner" width="100%">
</p>

<p align="center">
  <strong>Event-driven SaaS that turns Telegram group chatter into scored sales leads.</strong>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/build-passing-brightgreen" alt="Build"></a>
  <a href="#"><img src="https://img.shields.io/badge/version-0.1.0-blue" alt="Version"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="#license"><img src="https://img.shields.io/badge/license-Proprietary-lightgrey" alt="License"></a>
</p>

<p align="center">
  <a href="#about-the-project">About</a> ·
  <a href="#key-features">Features</a> ·
  <a href="#getting-started">Getting Started</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#contributing">Contributing</a>
</p>

---

## About The Project

Sales teams miss buying-intent messages buried in Telegram groups. This system listens to those conversations in real time, matches them against tenant keywords (exact, fuzzy, and preset packs), scores them as **low / warm / hot** leads, and pushes a formatted alert to Telegram Saved Messages.

It is a **modular monolith**: one codebase, four bounded modules (`listener`, `processor`, `notification`, `admin_and_api`), shared Postgres models, and Redis as the Celery broker.

> Replace `docs/banner.png` with your logo or architecture diagram.

**Demo / screenshots:** _not published yet_ — add links here when available.

---

## Key Features

- **Telethon listener** — ingest incoming group/channel messages with StringSession auth
- **Celery matching engine** — RapidFuzz + keyword presets (`programmer`, `web_designer`, `seo_specialist`)
- **Lead scoring** — intent score and `LeadLevelEnum` (`low` / `warm` / `hot`)
- **Saved Messages alerts** — markdown notification with chat, sender, keywords, and message link
- **JWT REST API** — register / login / me with bcrypt passwords (`passlib`)
- **Keyword CRUD** — per-user positive/negative keywords
- **License status & renew** — subscription days remaining; admin-only renew (`is_admin`)
- **Async Postgres** — SQLAlchemy 2.0 + Alembic migrations
- **Docker Compose** — PostgreSQL 15 and Redis 7 with healthchecks

---

## Built With

| Layer | Stack |
|--------|--------|
| Runtime | Python 3.11+ |
| Ingest | [Telethon](https://docs.telethon.dev/) ≥ 1.36 |
| API | [FastAPI](https://fastapi.tiangolo.com/) ≥ 0.115, Uvicorn |
| Auth | Passlib/bcrypt, python-jose (JWT HS256) |
| Workers | Celery ≥ 5.4, Redis ≥ 5.2 (RESP2-compatible) |
| Database | PostgreSQL 15, SQLAlchemy 2.0 (async), asyncpg, Alembic |
| Matching | RapidFuzz |
| Admin UI | SQLAdmin (dashboard scaffold) |
| Ops | Docker Compose 3.9 |

<p>
  <img src="https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white" alt="Redis">
  <img src="https://img.shields.io/badge/Celery-5.4-37814A?logo=celery&logoColor=white" alt="Celery">
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white" alt="SQLAlchemy">
</p>

---

## Architecture

```
Telegram groups  →  listener (Telethon)
                         │
                         ▼
                   Celery / Redis
                         │
                         ▼
              processor (match + score)
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
     notification                 Postgres
     (Saved Messages)             (users, keywords, leads)
            ▲
            │
     FastAPI /api/v1  (JWT, keywords, licenses)
```

| Module | Path | Role |
|--------|------|------|
| Listener | `modules/listener/` | Telethon ingest → Celery task |
| Processor | `modules/processor/` | Normalize, match, score, enqueue notify |
| Notification | `modules/notification/` | Format + send to `me` |
| Admin & API | `modules/admin_and_api/` | FastAPI + SQLAdmin |

---

## Getting Started

### Prerequisites

- Python **3.11+**
- Docker & Docker Compose
- Telegram `api_id` / `api_hash` from [my.telegram.org](https://my.telegram.org)
- (Optional) Git

### Installation

```bash
git clone <YOUR_REPO_URL>.git
cd self-bot

python -m venv venv
# Windows: .\venv\Scripts\activate
# Unix:    source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
```

Start infrastructure (Postgres is published on **host port 5433**):

```bash
docker compose up -d postgres redis
```

Apply schema:

```bash
alembic upgrade head
```

### Environment Setup

Create `.env` (see `.env.example`). Minimum:

```dotenv
# App / JWT
APP_ENV=development
LOG_LEVEL=INFO
SECRET_KEY=replace-with-a-long-random-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# PostgreSQL (host apps → 5433; in-compose services use host "postgres" / 5432)
POSTGRES_USER=telegram_listener
POSTGRES_PASSWORD=changeme
POSTGRES_DB=telegram_listener
POSTGRES_HOST=localhost
POSTGRES_PORT=5433

# Redis / Celery
REDIS_URL=redis://127.0.0.1:6379/0

# Telegram
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
```

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT signing key |
| `POSTGRES_*` | Async SQLAlchemy / Alembic |
| `REDIS_URL` | Celery broker and result backend |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Telethon client |

---

## Usage

### Run services (development)

```bash
# API  → http://127.0.0.1:8000/docs
uvicorn modules.admin_and_api.main:app --reload --host 0.0.0.0 --port 8000

# Matching worker (solo pool recommended on Windows)
python -m modules.processor.worker

# Telegram listener
python -m modules.listener.app
```

Full stack via Compose (after a `Dockerfile` is in place):

```bash
docker compose up -d
```

### API (v0.1)

Interactive OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/api/v1/auth/register` | No |
| `POST` | `/api/v1/auth/login` | No (OAuth2 form) |
| `GET` | `/api/v1/auth/me` | Bearer JWT |
| `GET/POST` | `/api/v1/keywords/` | Bearer JWT |
| `PUT/DELETE` | `/api/v1/keywords/{keyword_id}` | Bearer JWT |
| `GET` | `/api/v1/licenses/status` | Bearer JWT |
| `POST` | `/api/v1/licenses/renew` | Bearer JWT + admin |

Login and call `/me`:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -d "username=alice&password=secret123" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/auth/me
```

---

## Project Layout

```text
self-bot/
├── alembic/                  # Migrations
├── config/presets/           # Business-type keyword packs
├── core/                     # Config, DB, Redis, logging, JWT/bcrypt
├── shared/                   # ORM models & enums
└── modules/
    ├── listener/
    ├── processor/
    ├── notification/
    └── admin_and_api/
```

---

## Contributing

This repository is currently a private/team product. If you have access:

1. Branch from `main` (`feat/…`, `fix/…`).
2. Keep PRs focused; match existing module boundaries.
3. Do not commit `.env`, session strings, or secrets.
4. Open a PR with a short “why” and a test note (API path or worker scenario).

---

## License

**Proprietary — All rights reserved.** Unauthorized copying, distribution, or use is prohibited unless you have a written agreement with the owners.

<!-- Swap the badge and this section if you later publish under MIT / Apache-2.0. -->
