FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps for psycopg2 + cryptography wheels are bundled; build-essential kept minimal.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

# Storage dir for local-disk resume files; logs dir for app.log (also created at
# runtime by configure_logging(), but pre-creating mirrors the storage pattern).
RUN mkdir -p /app/storage /app/logs

EXPOSE 8000

# On boot: apply migrations, seed (idempotent), then serve.
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
