# demogorgux

AI demo agent that joins a simulated call, shares a virtual browser screen, and answers via chat while navigating the product.

## Architecture

- `backend/`: FastAPI + Playwright + Anthropic Computer Use loop
- `frontend/`: React "video call simulation" UI
- Integrated mode: FastAPI serves the built frontend and API from one app (`http://localhost:8000`)

## Prerequisites

- Python 3.10+
- Node.js 18+
- `ANTHROPIC_API_KEY` in `.env`

Optional (for starting already logged in to Monkeytype):
- `DEMO_LOGIN_EMAIL` in `.env`
- `DEMO_LOGIN_PASSWORD` in `.env`

## Install

```bash
pip install -r requirements.txt
cd frontend && npm install
```

## Run Integrated App (recommended)

```bash
cd frontend && npm run build
cd ..
uvicorn backend.server.api:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` and click **Launch Demo**.

### Notes

- On first successful login, browser session state is saved to `auth_state.json` and reused automatically on next runs.
- If your Anthropic SDK version does not support the `betas` argument, the backend now falls back automatically.

## Run Split Dev Mode (optional)

Terminal 1:
```bash
uvicorn backend.server.api:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2:
```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.
