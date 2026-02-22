import os
import asyncio
import base64
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend.agent.computer_use import run_computer_use_loop
from backend.agent.state import SessionState
from backend.browser.controller import start_browser, take_screenshot, close_browser, navigate_to
from backend.tts import generate_speech, TTS_ENABLED
from backend.stt import transcribe_audio, STT_ENABLED

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
DEMO_START_URL = os.getenv("DEMO_START_URL", "about:blank")

# Matches sentence-ending punctuation optionally followed by whitespace.
SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s*$')
# Matches clause-boundary punctuation (comma, semicolon, colon, dash, newline).
CLAUSE_BREAK_RE = re.compile(r'(?<=[,;:\u2014\-\n])\s*$')
CLAUSE_FLUSH_MIN_CHARS = 60  # only flush on clause boundary if buffer is long enough
# Approximate reading speed for dynamic delay when TTS is disabled (~150 WPM).
READING_CHARS_PER_SEC = 12.5
MAX_READING_DELAY = 5.0  # cap delay to avoid excessively long waits
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _get_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS")
    if raw:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        return origins or DEFAULT_CORS_ORIGINS
    return DEFAULT_CORS_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting server and launching Playwright...")
    await start_browser(start_url=DEMO_START_URL)
    yield
    logger.info("Shutting down server and closing browser...")
    await close_browser()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str
    url: str | None = None


class NavigateRequest(BaseModel):
    url: str


sessions: dict[str, SessionState] = {}
session_tasks: dict[str, asyncio.Task] = {}
session_cancel_events: dict[str, asyncio.Event] = {}


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    if request.session_id not in sessions:
        sessions[request.session_id] = SessionState(
            session_id=request.session_id,
            target_url=request.url or "",
        )

    session = sessions[request.session_id]
    if request.url:
        session.target_url = request.url

    # Cancel any existing agent task for this session gracefully
    was_interrupted = False
    existing_task = session_tasks.get(request.session_id)
    if existing_task and not existing_task.done():
        was_interrupted = True
        # Signal the agent loop to stop gracefully before cancelling
        cancel_evt = session_cancel_events.get(request.session_id)
        if cancel_evt:
            cancel_evt.set()
        existing_task.cancel()
        try:
            await existing_task
        except asyncio.CancelledError:
            logger.info(f"Cancelled previous task for session {request.session_id}")
        except Exception as e:
            logger.warning(f"Previous task ended with error for session {request.session_id}: {e}")

    # Create a fresh cancel event for this request
    cancel_event = asyncio.Event()
    session_cancel_events[request.session_id] = cancel_event

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        # --- TTS infrastructure ---
        text_buffer: list[str] = []
        tts_sentence_queue: asyncio.Queue = asyncio.Queue()
        # Tracks whether the TTS worker has finished all queued sentences.
        # Used by on_before_actions to wait until narration audio is generated
        # before executing browser actions (speak-then-act pacing).
        tts_idle = asyncio.Event()
        tts_idle.set()  # idle initially — no pending work

        async def tts_worker():
            """Sequential worker: reads sentences, generates speech, pushes audio SSE events."""
            while True:
                sentence = await tts_sentence_queue.get()
                if sentence is None:
                    tts_idle.set()
                    break
                try:
                    audio_bytes = await generate_speech(sentence)
                    if audio_bytes:
                        b64 = base64.b64encode(audio_bytes).decode("ascii")
                        await queue.put(json.dumps({"type": "audio", "content": b64}))
                except Exception as e:
                    logger.error(f"TTS worker error: {e}")
                finally:
                    if tts_sentence_queue.empty():
                        tts_idle.set()

        def _flush_sentence_from_buffer() -> None:
            """Check if buffer contains a complete sentence or long clause; if so, queue it for TTS."""
            joined = "".join(text_buffer)
            # Always flush on sentence boundaries
            if SENTENCE_END_RE.search(joined):
                sentence = joined.strip()
                if sentence:
                    tts_idle.clear()
                    tts_sentence_queue.put_nowait(sentence)
                text_buffer.clear()
                return
            # Also flush on clause boundaries when buffer is long enough
            if len(joined) >= CLAUSE_FLUSH_MIN_CHARS and CLAUSE_BREAK_RE.search(joined):
                clause = joined.strip()
                if clause:
                    tts_idle.clear()
                    tts_sentence_queue.put_nowait(clause)
                text_buffer.clear()

        async def on_text(text: str):
            await queue.put(json.dumps({"type": "token", "content": text}))
            if TTS_ENABLED:
                text_buffer.append(text)
                _flush_sentence_from_buffer()

        async def on_tool(action: str):
            # Flush any buffered text to TTS before action execution starts,
            # so audio generates DURING action delays instead of after.
            if TTS_ENABLED:
                remaining = "".join(text_buffer).strip()
                if remaining:
                    tts_sentence_queue.put_nowait(remaining)
                text_buffer.clear()
            await queue.put(json.dumps({"type": "tool_start", "content": f"Action: {action}"}))

        async def on_screenshot(b64: str):
            await queue.put(json.dumps({"type": "screenshot", "content": b64}))

        async def on_cursor_move(x: int, y: int):
            await queue.put(json.dumps({"type": "cursor_move", "x": x, "y": y}))

        async def on_before_actions(text_chars: int):
            """Wait for narration to be consumed before executing browser actions.

            When TTS is enabled, flushes any remaining text buffer and waits
            for the TTS worker to finish generating audio for all queued
            sentences (speak-then-act pacing).

            When TTS is disabled, sleeps for a duration proportional to the
            amount of text streamed this iteration, approximating reading time.
            """
            if TTS_ENABLED:
                # Flush any remaining buffered text to TTS
                remaining = "".join(text_buffer).strip()
                if remaining:
                    tts_idle.clear()
                    tts_sentence_queue.put_nowait(remaining)
                    text_buffer.clear()
                # Wait for TTS worker to finish all queued sentences
                await tts_idle.wait()
            else:
                # Dynamic delay based on text length (~150 WPM)
                if text_chars > 0:
                    delay = min(text_chars / READING_CHARS_PER_SEC, MAX_READING_DELAY)
                    await asyncio.sleep(delay)

        tts_task = asyncio.create_task(tts_worker()) if TTS_ENABLED else None

        async def run_agent():
            try:
                await run_computer_use_loop(
                    session=session,
                    user_message=request.message,
                    on_text_delta=on_text,
                    on_tool_action=on_tool,
                    on_screenshot=on_screenshot,
                    on_cursor_move=on_cursor_move,
                    on_before_actions=on_before_actions,
                    cancel_event=cancel_event,
                )
            except Exception as e:
                logger.error(f"Agent error: {e}")
                await queue.put(json.dumps({"type": "token", "content": f"Sorry, an error occurred: {str(e)}"}))
            finally:
                # Flush any remaining text in the buffer as a final sentence
                if TTS_ENABLED:
                    remaining = "".join(text_buffer).strip()
                    if remaining:
                        await tts_sentence_queue.put(remaining)
                    text_buffer.clear()
                    await tts_sentence_queue.put(None)  # signal TTS worker to exit

                # Wait for TTS worker to finish all queued sentences
                if tts_task:
                    try:
                        await tts_task
                    except Exception as e:
                        logger.error(f"TTS task error on shutdown: {e}")

                await queue.put(None)  # sentinel for SSE stream

        task = asyncio.create_task(run_agent())
        session_tasks[request.session_id] = task

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {item}\n\n"

            yield f"data: {json.dumps({'type': 'end'})}\n\n"
            await task  # propagate exceptions
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if session_tasks.get(request.session_id) is task:
                session_tasks.pop(request.session_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/navigate")
async def navigate_endpoint(request: NavigateRequest):
    """Navigate the browser to a new URL and return a screenshot."""
    screenshot_b64 = await navigate_to(request.url)
    return {"screenshot": screenshot_b64}


@app.get("/screenshot")
async def get_screenshot():
    """Returns the current browser screenshot for initial page load."""
    b64 = await take_screenshot()
    return {"screenshot": b64}


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    """Transcribe audio using ElevenLabs Speech-to-Text."""
    if not STT_ENABLED:
        raise HTTPException(status_code=503, detail="STT not configured (missing ELEVENLABS_API_KEY)")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    content_type = file.content_type or "audio/webm"
    transcript = await transcribe_audio(audio_bytes, content_type)

    if transcript is None:
        raise HTTPException(status_code=500, detail="Transcription failed")

    return {"transcript": transcript}


@app.get("/health")
async def healthcheck():
    return {"status": "ok"}


def _resolve_frontend_asset_path(path: str) -> Path:
    relative_path = path.lstrip("/")
    candidate = (FRONTEND_DIST_DIR / relative_path).resolve()
    dist_root = FRONTEND_DIST_DIR.resolve()

    # Guard against directory traversal and only serve files from dist.
    if not str(candidate).startswith(str(dist_root)):
        raise HTTPException(status_code=404, detail="Not found")

    return candidate


@app.get("/")
async def serve_frontend_index():
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build not found. Run 'npm run build' in frontend/.",
        )
    return FileResponse(FRONTEND_INDEX_FILE)


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build not found. Run 'npm run build' in frontend/.",
        )

    asset_path = _resolve_frontend_asset_path(full_path)
    if asset_path.is_file():
        return FileResponse(asset_path)

    # React Router SPA fallback for routes like /demo
    return FileResponse(FRONTEND_INDEX_FILE)
