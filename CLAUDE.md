# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Demogorgux is an AI-powered automated product demonstration system using Claude's Computer Use capabilities. An agent persona ("Demogorgux", a Sales Engineer) navigates web applications via headless browser, answers questions, and demos features through a real-time streaming interface. Currently configured to demo Monkeytype (monkeytype.com).

## Commands

### Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run server (from repo root)
cd backend && uvicorn server.api:app --reload --port 8000

# Interactive CLI test (useful for debugging without frontend)
cd backend && python test_agent.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Dev server on port 5173
npm run build    # Production build
npm run preview  # Preview production build
```

### Environment
Requires `ANTHROPIC_API_KEY` environment variable (or `.env` file via python-dotenv).

## Architecture

### Data Flow
User input (text or voice) → Frontend SSE POST to `/chat` → FastAPI backend → Intent guard (Haiku classifier rejects off-topic) → Screenshot capture → Claude Sonnet with Computer Use tool → Agentic loop (execute actions, screenshot, re-prompt, max 15 iterations) → Stream SSE events back (`token`, `tool_start`, `screenshot`, `end`).

### Backend (`backend/`)
- **`server/api.py`** — FastAPI app with SSE streaming. Two endpoints: `POST /chat` (agent loop) and `GET /screenshot` (current page). CORS open for frontend. Playwright lifecycle managed via FastAPI lifespan.
- **`agent/computer_use.py`** — Core agent loop (`run_computer_use_loop()`). Two models: `claude-sonnet-4-20250514` for reasoning, `claude-haiku-4-5-20251001` for intent guard. Keeps last 5 message pairs for context. Streams callbacks to frontend.
- **`agent/prompts.py`** — System prompt defining Alex's persona, product knowledge, and demo flow. Intent guard prompt for on/off-topic classification.
- **`agent/state.py`** — Session state dataclass (session_id, messages, current_url, demo_stage, auth status, last screenshot).
- **`browser/controller.py`** — Playwright headless Chromium (1280x800 viewport). Manages auth persistence via `auth_state.json`. Injects fake CSS cursor for visual feedback.
- **`browser/actions.py`** — Maps Claude Computer Use tool calls to Playwright commands (clicks, typing, scrolling, dragging, key combos).

### Frontend (`frontend/`)
- React 18 + Vite + Tailwind CSS (dark theme).
- **Pages:** Landing (`/`) and Demo (`/demo`) via React Router v6.
- **`hooks/useChat.js`** — Fetch-based SSE client for `/chat`. Parses streaming events, manages chat history and session ID.
- **`hooks/useSpeech.js`** — Web Speech API wrapper for voice input (continuous listening, final transcripts only).
- **Components:** `ChatPanel` (message display), `ScreenShare` (screenshot viewer), `ControlBar` (mic/camera toggles with getUserMedia for PiP).

### Key Design Decisions
- Agent understands UI via screenshots (vision), not DOM inspection.
- Communication uses Server-Sent Events for real-time streaming (not WebSockets).
- Browser auth state persists across sessions via `auth_state.json` (git-ignored).
- No test framework or linter configured yet.
