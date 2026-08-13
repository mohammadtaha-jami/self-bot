# Telegram Opportunity Detection & Lead Intelligence System

Production-grade, event-driven SaaS application for detecting business opportunities and leads from Telegram channels and groups.

## Architecture

Modular Monolith with four bounded modules:

| Module | Phase | Responsibility |
|--------|-------|----------------|
| `listener` | 2 | Telethon client; ingests raw messages |
| `processor` | 3 | Background worker; keyword matching & NLP scoring |
| `notification` | 4 | Lead alert delivery |
| `admin_and_api` | 5 | FastAPI REST API & SQLAdmin dashboard |

## Project Structure

```
telegram_listener_project/
├── core/           # Shared infrastructure (config, DB, cache, logging)
├── shared/         # Domain models & enums
└── modules/        # Feature modules (listener, processor, notification, admin_and_api)
```

## Quick Start

1. Copy environment template:
   ```bash
   cp .env.example .env
   ```

2. Start infrastructure:
   ```bash
   docker compose up -d postgres redis
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run services (development):
   ```bash
   python -m modules.listener.app
   python -m modules.processor.worker
   uvicorn modules.admin_and_api.main:app --reload
   ```

## Environment Variables

See `.env.example` for required configuration.

## License

Proprietary — All rights reserved.
