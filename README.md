# DemoX

AI-powered website demo system. Paste any URL, join a live video call, and an AI agent conducts a narrated screen-sharing demo of that website in real time.

## How It Works

A **Presenter Agent** joins a LiveKit video call, opens the website in a Playwright browser, shares its screen, and narrates a live demo using voice (Deepgram STT + ElevenLabs TTS). A **Researcher Agent** crawls the website in parallel and feeds intelligence to the presenter via Redis.

## Prerequisites

- Python 3.12+
- Node.js 20+
- Redis (local install or Docker)
- API keys (see [Environment Variables](#environment-variables))

## Setup

1. Clone the repository:

```bash
git clone https://github.com/DUKITROX/demogorgux.git
cd demogorgux
```

2. Create a `.env` file in the project root with all required keys:

```
LIVEKIT_URL=wss://your-livekit-instance.livekit.cloud
LIVEKIT_API_KEY=your-livekit-api-key
LIVEKIT_API_SECRET=your-livekit-api-secret
ANTHROPIC_API_KEY=sk-ant-...
DEEPGRAM_API_KEY=your-deepgram-key
ELEVENLABS_API_KEY=sk_...
REDIS_URL=redis://localhost:6379
```

## Running

### One Command (recommended)

```bash
./run.sh
```

This will automatically:
- Create a Python virtual environment (`.venv`)
- Install all Python dependencies
- Download the Playwright Chromium browser
- Start Redis via Docker if not already running
- Build and start the Next.js frontend
- Start the FastAPI backend
- Start the Presenter Agent worker

Once everything is up, open [http://localhost:3000](http://localhost:3000).

### Manual (3 terminals)

```bash
# Terminal 1: Backend API
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Presenter Agent worker
source .venv/bin/activate
python -m presenter_agent.agent dev

# Terminal 3: Frontend
cd frontend && npm run dev
```

> Make sure Redis is running before starting the backend (`redis-server` or `docker run -d -p 6379:6379 redis:7-alpine`).

### Docker Compose

```bash
docker-compose up
```

This starts all services (Redis, backend, presenter agent, frontend) together.

## Environment Variables

| Variable | Service | Notes |
|---|---|---|
| `LIVEKIT_URL` | LiveKit Cloud | WebSocket URL for your LiveKit instance |
| `LIVEKIT_API_KEY` | LiveKit Cloud | For room creation + token signing |
| `LIVEKIT_API_SECRET` | LiveKit Cloud | JWT signing secret |
| `ANTHROPIC_API_KEY` | Anthropic | Powers both presenter LLM and researcher extraction |
| `DEEPGRAM_API_KEY` | Deepgram | Speech-to-text for user audio |
| `ELEVENLABS_API_KEY` | ElevenLabs | Text-to-speech for agent voice |
| `REDIS_URL` | Redis | Default: `redis://localhost:6379` |

## Project Structure

```
backend/
  main.py              - FastAPI app (POST /api/demo/start, GET /status, DELETE /stop)
  config.py            - Loads env vars from .env
  room_manager.py      - LiveKit room creation + JWT token generation
  agent_launcher.py    - Spawns researcher subprocess per room
  redis_bus.py         - Redis pub/sub and key-value helpers

presenter_agent/
  agent.py             - LiveKit agent entrypoint (Agent + AgentSession)
  screen_share.py      - Playwright screenshots -> LiveKit video track
  tools.py             - Agent tools: navigate, click, scroll, highlight, research

researcher_agent/
  researcher.py        - Crawl -> extract -> summarize -> publish to Redis
  extractor.py         - Claude-powered knowledge extraction per page
  summarizer.py        - Generates step-by-step demo script

frontend/src/
  app/page.tsx         - Landing page with URL input
  app/demo/[roomId]/   - Live call page
  components/          - CallView, AgentScreenShare, UserMicControl, AgentStatus, Transcript
```
