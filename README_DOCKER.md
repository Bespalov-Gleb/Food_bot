# Docker quickstart

1. Copy environment:
   cp .env.example .env
   # fill BOT_TOKEN, SUPER_ADMIN_IDS etc.

2. Build and start stack:
   docker compose up -d --build migrate
   docker compose up -d --build api bot

3. Open API: http://localhost:8000

Notes:
- DATABASE_URL points to Postgres in docker-compose (service `db`).
- Alembic runs in `migrate` service; re-run `docker compose run --rm migrate python -m alembic upgrade head` after model changes.