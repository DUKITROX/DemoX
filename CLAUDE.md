# DemoX — AI-Powered Website Demo System

## What This Project Is

A two-agent AI system where a user pastes any website URL, joins a LiveKit video call, and an AI agent conducts a live narrated demo of that website — sharing its screen and talking in real time. A second agent researches the website in parallel and feeds intelligence to the presenter.

## Architecture

```
User Browser (Next.js :3000)
    ↕ HTTPS          ↕ WebRTC (LiveKit Cloud)
FastAPI Backend (:8000)    LiveKit Server (wss://demox-wvrqi22d.livekit.cloud)
    │ spawns                    ↑ publishes tracks
    ↓                           │
┌─────────────────────────────────────┐
│  Presenter Agent (LiveKit worker)   │  ← voice pipeline + screen share
│  Researcher Agent (subprocess)      │  ← crawls site, extracts knowledge
│  Redis (:6379)                      │  ← inter-agent communication bus
└─────────────────────────────────────┘
```

## Key Technical Decisions

### Voice Pipeline: Deepgram STT + ElevenLabs TTS (not Cartesia)
The original plan called for Cartesia TTS. We switched to ElevenLabs because the user already had an ElevenLabs API key, avoiding an extra service dependency. Deepgram was chosen for STT due to its best-in-class LiveKit plugin support and free tier.

### livekit-agents 1.4.x API (Agent + AgentSession, not VoicePipelineAgent)
The plan referenced the older `VoicePipelineAgent` API. The installed `livekit-agents==1.4.2` uses a new API:
- `Agent(instructions=..., stt=..., llm=..., tts=..., tools=...)` — declarative agent definition
- `AgentSession().start(agent=..., room=...)` — session lifecycle
- `@function_tool` decorator — replaces the old `FunctionContext` class
- `RunContext` as first param to all tools

### Presenter Agent runs as a LiveKit Worker (not per-room subprocess)
The plan suggested spawning presenter agents per room. LiveKit's agent framework is designed as a **worker model** — one long-running process that auto-dispatches to rooms when participants join. This is more efficient and is the officially supported pattern. Run with: `python -m presenter_agent.agent dev`

### Researcher Agent runs as a subprocess per room
Unlike the presenter, the researcher has no LiveKit integration. The backend spawns it as a subprocess with `ROOM_ID` and `WEBSITE_URL` env vars. It crawls, extracts, and publishes to Redis, then monitors for deep-dive requests.

### Screen Share: Playwright screenshots → VideoFrame → LiveKit VideoSource
LiveKit doesn't natively capture Playwright browsers. We run a capture loop at 15fps:
1. `page.screenshot(type="jpeg", quality=75)` — fast JPEG capture
2. Convert to RGBA via Pillow
3. Create `rtc.VideoFrame(type=VideoBufferType.RGBA)`
4. Push to `rtc.VideoSource` published as `TrackSource.SOURCE_SCREEN_SHARE`

### Inter-agent Communication: Redis pub/sub + key-value
- `research:{room_id}` — key storing latest research JSON (researcher writes, presenter reads)
- `research_updates:{room_id}` — pub/sub channel for live research updates
- `agent_requests:{room_id}` — pub/sub channel for presenter → researcher deep-dive requests
- `room:{room_id}` — room metadata (URL, status) with 1h TTL

### Frontend proxies API calls via Next.js rewrites
Instead of CORS complexity, `next.config.ts` rewrites `/api/*` to the FastAPI backend. The frontend stores LiveKit tokens in `sessionStorage` keyed by room ID.

## Project Structure

```
backend/
  main.py              — FastAPI app, POST /api/demo/start, GET /status, DELETE /stop
  config.py            — loads all env vars from .env
  room_manager.py      — LiveKit room creation + JWT token generation
  agent_launcher.py    — spawns researcher subprocess; presenter is a worker (no spawn needed)
  redis_bus.py         — Redis helpers for pub/sub and key-value operations

presenter_agent/
  agent.py             — LiveKit agent entrypoint (Agent + AgentSession + cli.run_app)
  screen_share.py      — BrowserScreenShare class (Playwright → LiveKit video track)
  tools.py             — @function_tool definitions: navigate, click, scroll, highlight, research

researcher_agent/
  researcher.py        — Main pipeline: crawl → extract → summarize → publish to Redis
  extractor.py         — Claude-powered structured knowledge extraction per page
  summarizer.py        — Generates a step-by-step demo script from combined knowledge

frontend/src/
  app/page.tsx         — Landing page with URL input form
  app/demo/[roomId]/   — Dynamic route for live call
  components/          — CallView, AgentScreenShare, UserMicControl, AgentStatus, Transcript
```

## Running Locally

### Prerequisites
- Python 3.12+ with `.venv` at project root
- Node.js 20+
- Redis (local or via Docker)
- Playwright Chromium: `.venv/bin/playwright install chromium`

### One Command
```bash
./run.sh
```

### Manual (3 terminals)
```bash
# Terminal 1: Backend API
.venv/bin/uvicorn backend.main:app --port 8000

# Terminal 2: Presenter agent worker
.venv/bin/python -m presenter_agent.agent dev

# Terminal 3: Frontend
cd frontend && npm run dev
```

### Docker
```bash
docker-compose up
```

## Environment Variables (.env)

| Variable | Service | Notes |
|---|---|---|
| `LIVEKIT_URL` | LiveKit Cloud | `wss://demox-wvrqi22d.livekit.cloud` |
| `LIVEKIT_API_KEY` | LiveKit Cloud | For room creation + token signing |
| `LIVEKIT_API_SECRET` | LiveKit Cloud | JWT signing secret |
| `ANTHROPIC_API_KEY` | Anthropic | Powers both presenter LLM and researcher extraction |
| `DEEPGRAM_API_KEY` | Deepgram | Speech-to-text for user audio |
| `ELEVENLABS_API_KEY` | ElevenLabs | Text-to-speech for agent voice |
| `REDIS_URL` | Redis | Default: `redis://localhost:6379` |

## Important Patterns

### How the demo flow works
1. User submits URL on frontend → `POST /api/demo/start`
2. Backend creates LiveKit room with URL in metadata, generates user token
3. Backend spawns researcher subprocess (starts crawling immediately)
4. User joins room via frontend → LiveKit dispatches presenter agent to room
5. Presenter reads URL from room metadata, opens Playwright browser, starts screen share
6. Presenter greets user and begins demo, using research context when available
7. Research updates flow via Redis pub/sub → presenter updates its instructions dynamically

### How tools work
The presenter agent has 7 tools: `navigate_to`, `click_element`, `scroll_down`, `scroll_to_element`, `highlight_element`, `get_research_context`, `request_deep_dive`. All take `RunContext` as first param. The LLM decides when to call them during the conversation.

### How research context gets injected
The presenter builds its `instructions` string with research data embedded. A background task subscribes to `research_updates:{room_id}` and calls `agent.update_instructions()` when new research arrives.

## Python Package Note
Directory names use underscores (`presenter_agent/`, `researcher_agent/`) because Python module names cannot contain hyphens. The old empty `presenter-agent/` and `researcher-agent/` directories from the initial plan can be deleted.
