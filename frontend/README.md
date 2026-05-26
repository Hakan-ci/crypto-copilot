# MEXC Futures Trade Review Frontend

Next.js MVP frontend for the read-only MEXC Futures trade-review co-pilot.

## Local Setup

Run the FastAPI backend first. Once it is running, open a second terminal:

```bash
cd /home/hakan/Desktop/crypto-copilot/frontend
npm install
cp .env.example .env.local
npm run dev
```

By default the frontend calls:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Run the FastAPI backend separately:

```bash
cd /home/hakan/Desktop/crypto-copilot/backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload
```

Open `http://localhost:3000`. The app redirects to `/dashboard`.

Paste the backend development user UUID into the header field and click Save. If you have not created one yet, run this from the backend directory after migrations:

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

## Checks

```bash
cd frontend
npm run lint
npm run typecheck
```

## Safety

This frontend is read-only. It does not sign MEXC requests and does not include any exchange trading controls. MEXC API signing stays on the backend.
