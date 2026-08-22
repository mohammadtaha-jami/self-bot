# Telegram Listener Project Structure

```text
self-bot/
├── .env.example
├── docker-compose.yml
├── requirements.txt
├── README.md
├── alembic.ini
│
├── alembic/                        # Database migrations (Alembic)
│   ├── env.py
│   └── versions/
│
├── config/
│   └── presets/                    # Keyword presets per business type
│       ├── programmer.json
│       ├── web_designer.json
│       └── seo_specialist.json
│
├── core/
│   ├── __init__.py
│   ├── config.py                   # Pydantic BaseSettings (DB, Redis, JWT)
│   ├── database.py                 # SQLAlchemy async engine & session factory
│   ├── cache.py                    # Redis async connection pool
│   ├── logger.py                   # Structured logging setup
│   └── security.py                 # bcrypt password hashing + JWT access tokens
│
├── shared/
│   ├── __init__.py
│   ├── models.py                   # ORM: User, TelegramSession, Keyword, Source, Person, Message, Lead, Feedback
│   └── enums.py                    # LeadLevelEnum, KeywordTypeEnum, FeedbackTypeEnum
│
└── modules/
    ├── __init__.py
    ├── listener/                   # Phase 2 — Telethon ingest
    │   ├── __init__.py
    │   ├── app.py                  # Client startup
    │   ├── auth.py                 # StringSession login
    │   ├── handlers.py             # NewMessage → payload (incl. session_string)
    │   └── producer.py             # Dispatch Celery task
    ├── processor/                  # Phase 3 — matching worker
    │   ├── __init__.py
    │   ├── worker.py               # Celery app (Redis RESP2-compatible)
    │   ├── tasks.py                # process_raw_message + publish_lead_notification
    │   ├── matching.py             # Keyword / fuzzy matching
    │   ├── nlp.py                  # Text cleaning
    │   └── presets.py              # Load JSON presets by business_type
    ├── notification/               # Phase 4 — Saved Messages alerts
    │   ├── __init__.py
    │   ├── sender.py               # Telethon send to "me"
    │   └── formatter.py            # Lead message markdown
    └── admin_and_api/              # Phase 5 — FastAPI
        ├── __init__.py
        ├── main.py                 # App factory; mounts /api/v1/auth
        ├── admin.py                # SQLAdmin (placeholder)
        ├── schemas.py              # User/Token + lead Pydantic schemas
        ├── deps.py                 # OAuth2 bearer, get_db, get_current_user
        └── routers/
            ├── __init__.py
            ├── auth.py             # POST /register, POST /login, GET /me
            └── leads.py            # Leads endpoints (placeholder)
```

## Phase 5.2 — Auth API (mounted in `main.py`)

| Method | Path | Auth | Notes |
|--------|------|------|--------|
| `POST` | `/api/v1/auth/register` | No | bcrypt hash; unique username / telegram_id; `201` |
| `POST` | `/api/v1/auth/login` | No | OAuth2 form → JWT (`Token`) |
| `GET` | `/api/v1/auth/me` | Bearer JWT | Active user only (`UserResponse`) |

Interactive docs: `/docs`
