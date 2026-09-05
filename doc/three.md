# Telegram Listener Project Structure

```text
self-bot/
├── .env.example
├── docker-compose.yml              # Postgres + Redis
├── Dockerfile
├── requirements.txt
├── README.md
├── alembic.ini
├── pyrightconfig.json
│
├── alembic/                        # Database migrations
│   ├── env.py
│   └── versions/
│       ├── 3fe7d1a5aca7_initial_tables.py
│       ├── a1b2c3d4e5f6_add_dashboard_password.py
│       ├── b2c3d4e5f6a7_add_is_engine_active.py
│       ├── c3d4e5f6a7b8_add_user_phone_and_telegram_username.py
│       └── d4e5f6a7b8c9_add_user_listen_folder.py
│
├── config/
│   └── presets/                    # Default keywords per business_type
│       ├── programmer.json
│       ├── web_designer.json
│       ├── seo_specialist.json
│       └── real_estate.json
│
├── core/
│   ├── __init__.py
│   ├── config.py                   # Pydantic BaseSettings (DB, Redis, JWT, Telegram)
│   ├── database.py                 # SQLAlchemy async engine & session factory
│   ├── cache.py                    # Redis: keywords, engine status, listen scope, heartbeats
│   ├── logger.py                   # Structured logging
│   └── security.py                 # bcrypt + JWT
│
├── shared/
│   ├── __init__.py
│   ├── models.py                   # User, TelegramSession, Keyword, Source, Person, Message, Lead, Feedback
│   ├── enums.py                    # LeadLevel, KeywordType, FeedbackType, BusinessType
│   └── telegram_session.py         # Pyrogram → Telethon StringSession conversion
│
├── tests/
│   ├── test_matching.py            # Word-boundary / fuzzy / HOT-WARM guards
│   └── test_dialog_filters.py      # Folder peer-id helpers
│
└── modules/
    ├── listener/                   # Telethon ingest (scoped by folder)
    │   ├── app.py                  # Loop: engine-active session + heartbeat
    │   ├── auth.py                 # load_client / interactive StringSession
    │   ├── dialog_filters.py       # GetDialogFiltersRequest → chat_id set
    │   ├── handlers.py             # NewMessage → Redis allowed_chats check → Celery
    │   └── producer.py             # Dispatch process_raw_message
    ├── processor/                  # Celery matching worker
    │   ├── worker.py               # Celery app (Redis RESP2)
    │   ├── tasks.py                # process_raw_message + publish_lead_notification
    │   ├── matching.py             # Rule engine (exact phrase + guarded fuzzy)
    │   ├── nlp.py                  # clean_text, tokenize, phrase match
    │   ├── persist.py              # Write Source / Person / Message / Lead
    │   └── presets.py              # JSON presets + user keyword Redis cache
    ├── notification/               # Saved Messages alerts
    │   ├── sender.py               # Telethon send to "me"
    │   └── formatter.py            # Lead markdown
    └── admin_and_api/              # FastAPI + HTML UI
        ├── main.py                 # App factory, /api/v1/* and HTML routes
        ├── admin.py                # SQLAdmin placeholder
        ├── schemas.py              # Pydantic request/response models
        ├── deps.py                 # JWT, cookie, get_db, admin guard
        ├── engine_pipeline.py      # Start/stop: license, session, folder, Redis, signals
        ├── routers/
        │   ├── auth.py             # register / login / logout / me
        │   ├── keywords.py         # User keyword bundle CRUD + Redis sync
        │   ├── licenses.py         # License status / renew
        │   ├── engine.py           # start / stop / status / pipeline / folders
        │   ├── telegram_auth.py    # Admin Telethon send-code / verify-code
        │   ├── admin.py            # Admin users, impersonate, telegram-sessions
        │   ├── users.py            # GET /api/v1/users
        │   └── leads.py            # List leads + feedback
        └── templates/
            ├── login.html
            ├── dashboard.html      # Tenant: engine toggle, folder dropdown, keywords
            ├── index.html          # Admin home
            ├── users.html          # Admin user CRUD + impersonate
            ├── sessions.html       # Admin telegram sessions + engine status
            ├── admin_gate.html
            ├── access_denied.html
            └── includes/           # admin_nav, session forms/scripts, common JS
```

## HTML UI routes (`main.py`)

| Path | Who | Template |
|------|-----|----------|
| `/login` | Public | `login.html` |
| `/dashboard` | Tenant | `dashboard.html` |
| `/`, `/admin` | Admin cookie | `index.html` |
| `/users` | Admin | `users.html` |
| `/sessions` | Admin | `sessions.html` |

## API (mounted in `main.py`)

Interactive docs: `/docs`

### Auth — `/api/v1/auth`

| Method | Path | Auth | Notes |
|--------|------|------|--------|
| `POST` | `/register` | No | Unique username / phone / telegram_id |
| `POST` | `/login` | No | OAuth2 form → JWT + cookie |
| `POST` | `/logout` | — | Clear cookie |
| `POST` | `/sync-cookie` | Bearer | HTML route guards |
| `GET` | `/me` | Bearer | `UserResponse` (username, phone, telegram_username) |

### Engine — `/api/v1/engine`

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/folders` | Telegram Dialog Filters for the user session; includes «همه» |
| `POST` | `/start` | Body `{ folder_id }` — Redis `user:{id}:allowed_chats` + `listen_scope` |
| `POST` | `/stop` | Clear engine flags and listen-scope cache |
| `GET` | `/status` | Engine, license, folder, keyword count |
| `GET` | `/pipeline` | Recent start/stop pipeline log |

### Keywords — `/api/v1/keywords`

Preset + custom merge; Redis `user:{id}:keywords`.

### Telegram attach (admin) — `/api/v1/telegram`

`POST /send-code`, `POST /verify-code` (Telethon StringSession).

### Admin — `/api/v1/admin`

Users CRUD, toggle-active, impersonate, renew-license, `GET /telegram-sessions` (engine on/off + listening).

### Other

| Prefix | Notes |
|--------|--------|
| `/api/v1/licenses` | Status / renew |
| `/api/v1/users` | List users |
| `/api/v1/leads` | List + feedback |

## Redis keys (runtime)

| Key | Purpose |
|-----|---------|
| `user:{id}:keywords` | Merged positive/negative keywords |
| `user:{id}:status` | `engine_active`, `license_valid` |
| `user:{id}:listen_scope` | `all` vs folder mode |
| `user:{id}:allowed_chats` | SET of Telegram chat_ids for folder scope |
| `user:{id}:pipeline_log` | Engine start/stop steps |
| `service:listener:heartbeat` | Listener liveness |
| `engine:control` | Pub/sub start/stop |

## User identity columns (`users`)

`username` = dashboard login only · `phone_number` · `telegram_id` · `telegram_username` · `listen_folder_id` / `listen_folder_title` (optional Dialog Filter).
