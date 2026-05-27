# Crypto Copilot

Read-only MEXC Futures trade-review workspace with a FastAPI backend and a Next.js frontend.

## Local Runbook

The backend runs on `http://127.0.0.1:8000`. The frontend runs on `http://localhost:3000`.

### 1. Install prerequisites

Verify the required tools:

```bash
python3 --version
node --version
npm --version
psql --version
```

Install anything missing:

- Python 3.11+ with `venv` support
- Node.js and npm, ideally a current LTS version
- PostgreSQL server and client tools

There is no Docker Compose file in this repo, so PostgreSQL must be started separately.

### 2. Create the local database

Create a PostgreSQL role and database:

```sql
CREATE USER crypto_copilot WITH PASSWORD 'crypto_copilot';
CREATE DATABASE crypto_copilot OWNER crypto_copilot;
```

Use this database URL in `backend/.env`:

```bash
postgresql+psycopg://crypto_copilot:crypto_copilot@localhost:5432/crypto_copilot
```

### 3. Set up the backend

```bash
cd /home/hakan/Desktop/crypto-copilot/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

Edit `backend/.env`:

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

Run migrations:

```bash
alembic upgrade head
```

Create a local development user and keep the printed UUID:

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

Start the API:

```bash
python -m uvicorn app.main:app --reload
```

Verify it:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

API docs are available at `http://127.0.0.1:8000/docs`.

### 4. Set up the frontend

Open a second terminal:

```bash
cd /home/hakan/Desktop/crypto-copilot/frontend
npm install
cp .env.example .env.local
npm run dev
```

`frontend/.env.local` should contain:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Open `http://localhost:3000`. The app redirects to `/dashboard`. Paste the development user UUID from the backend setup into the header field and click Save.

### 5. Use the MVP locally

- The Connect MEXC page is currently a placeholder; it does not persist credentials.
- Actual MEXC imports use `MEXC_ACCESS_KEY` and `MEXC_SECRET_KEY` from `backend/.env`.
- Use read-only MEXC Futures API keys only.
- Restart the backend after editing `backend/.env`.

Import history from the UI, then reconstruct positions with the backend endpoint:

```bash
curl -X POST "http://127.0.0.1:8000/users/YOUR_USER_UUID/symbols/BTC_USDT/reconstruct-positions"
```

After that, the dashboard and positions pages should have data.

## Checks

Backend:

```bash
cd /home/hakan/Desktop/crypto-copilot/backend
source .venv/bin/activate
ruff check .
pytest
```

Frontend:

```bash
cd /home/hakan/Desktop/crypto-copilot/frontend
npm run lint
npm run typecheck
```

## Notes

- Backend commands should be run from `backend` because settings load `.env` from the current working directory.
- Local CORS is enabled by default for `http://localhost:3000` and `http://127.0.0.1:3000`. Override it with `CORS_ALLOWED_ORIGINS` in `backend/.env`.
- The app is read-only. It must not place trades, cancel orders, change leverage, transfer funds, withdraw funds, or behave like a signal bot.
