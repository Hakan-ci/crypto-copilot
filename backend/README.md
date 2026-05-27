# MEXC Futures Trade Review Copilot Backend

FastAPI backend skeleton for a read-only MEXC Futures trade-review system. This app is for importing history, reconstructing positions, calculating indicator snapshots, journaling, risk review, checklist support, and future AI trade reviews.

It must not place trades, cancel orders, change leverage, transfer funds, withdraw funds, or behave like a signal bot.

## Local Setup

```bash
cd /home/hakan/Desktop/crypto-copilot/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` with your local PostgreSQL URL and secrets:

```bash
DATABASE_URL=postgresql+psycopg://crypto_copilot:crypto_copilot@localhost:5432/crypto_copilot
MEXC_BASE_URL=https://contract.mexc.com
APP_ENV=development
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
SECRET_KEY=replace-with-local-random-value
API_KEY_ENCRYPTION_KEY=replace-with-local-random-value
OPENAI_API_KEY=
OPENAI_REVIEW_MODEL=gpt-4o-mini
MEXC_ACCESS_KEY=
MEXC_SECRET_KEY=
```

Generate local secrets if desired:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Database

Create a PostgreSQL database first:

```sql
CREATE USER crypto_copilot WITH PASSWORD 'crypto_copilot';
CREATE DATABASE crypto_copilot OWNER crypto_copilot;
```

Then run migrations:

```bash
alembic upgrade head
```

Create a local development user and keep the printed UUID for the frontend header:

```bash
python - <<'PY'
from app.db.models import User
from app.db.session import get_sessionmaker

db = get_sessionmaker()()
user = User(email="local@example.com")
db.add(user)
db.commit()
print(user.id)
db.close()
PY
```

## Run The API

```bash
python -m uvicorn app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Checks

```bash
ruff check .
pytest
```

## Local Frontend Access

Local CORS is enabled by default for:

```bash
http://localhost:3000
http://127.0.0.1:3000
```

Override it with `CORS_ALLOWED_ORIGINS` in `.env`.

The Connect MEXC page is currently a placeholder; real imports use `MEXC_ACCESS_KEY` and `MEXC_SECRET_KEY` from `.env`.
