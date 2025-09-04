# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# No system compilers needed: using prebuilt wheels (psycopg2-binary)

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
# Add project root to PYTHONPATH for both api and bot
ENV PYTHONPATH="/app"

# Default command can be overridden in docker-compose
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000', timeout=3).status<500 else 1)"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

