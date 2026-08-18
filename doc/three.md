# Telegram Listener Project Structure

```text
self-bot/
├── .env.example
├── docker-compose.yml
├── requirements.txt
├── README.md
│
├── core/
│   ├── __init__.py
│   ├── config.py         # Pydantic BaseSettings + get_settings()
│   ├── database.py       # Async SQLAlchemy engine & session factory
│   ├── cache.py          # Redis async connection pool
│   └── logger.py         # Structured logging setup
│
├── shared/
│   ├── __init__.py
│   ├── models.py         # ORM placeholder (8 models documented)
│   └── enums.py          # LeadLevelEnum, KeywordTypeEnum, FeedbackTypeEnum
│
└── modules/
    ├── __init__.py
    ├── listener/         # Phase 2
    │   ├── __init__.py, app.py, auth.py, handlers.py, producer.py
    ├── processor/        # Phase 3
    │   ├── __init__.py, worker.py, tasks.py, matching.py, nlp.py
    ├── notification/     # Phase 4
    │   ├── __init__.py, sender.py
    └── admin_and_api/    # Phase 5
        ├── __init__.py, main.py, admin.py, schemas.py
        └── routers/
            ├── __init__.py, auth.py, leads.py