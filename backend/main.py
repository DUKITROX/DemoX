import asyncio
import logging
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import LIVEKIT_URL, LOGIN_URL, LOGIN_EMAIL, LOGIN_PASSWORD
from backend.room_manager import create_room_and_tokens, delete_room, ensure_agent_dispatched
from backend.agent_launcher import launch_presenter, launch_researcher, stop_agents
from backend.redis_bus import (
    set_room_metadata,
    get_room_metadata,
    get_research,
    cleanup_room,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DemoX API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartDemoRequest(BaseModel):
    url: str


class StartDemoResponse(BaseModel):
    room_id: str
    user_token: str
    livekit_url: str


@app.post("/api/demo/start", response_model=StartDemoResponse)
async def start_demo(request: StartDemoRequest):
    room_id = f"demo-{uuid4().hex[:8]}"

    # Attach credentials if the requested hostname matches the configured LOGIN_URL
    request_host = urlparse(request.url).hostname
    matched_email = LOGIN_EMAIL if (LOGIN_URL and request_host == LOGIN_URL) else None
    matched_password = LOGIN_PASSWORD if (LOGIN_URL and request_host == LOGIN_URL) else None

    # Create LiveKit room and tokens (credentials go into LiveKit room metadata
    # so the presenter agent can read them via ctx.room.metadata)
    tokens = await create_room_and_tokens(room_id, request.url, room_metadata={
        "login_email": matched_email,
        "login_password": matched_password,
    })

    # Store room metadata in Redis (for status tracking)
    await set_room_metadata(room_id, {
        "url": request.url,
        "status": "starting",
    })

    # Launch researcher immediately (background)
    launch_researcher(room_id, request.url)

    # Launch presenter agent
    launch_presenter(room_id, request.url)

    # Update status
    await set_room_metadata(room_id, {
        "url": request.url,
        "status": "active",
    })

    # Background task: re-dispatch agent if it hasn't joined after 10s
    async def _ensure_agent_joined():
        await asyncio.sleep(10)
        try:
            await ensure_agent_dispatched(room_id)
        except Exception as e:
            logger.error(f"Agent dispatch retry failed for {room_id}: {e}")

    asyncio.create_task(_ensure_agent_joined())

    return StartDemoResponse(
        room_id=room_id,
        user_token=tokens["user_token"],
        livekit_url=LIVEKIT_URL,
    )


@app.get("/api/demo/{room_id}/status")
async def get_demo_status(room_id: str):
    room = await get_room_metadata(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    research = await get_research(room_id)
    return {
        "room_id": room_id,
        "url": room.get("url"),
        "status": room.get("status"),
        "research_ready": research is not None and research.get("status") == "complete",
    }


@app.delete("/api/demo/{room_id}")
async def stop_demo(room_id: str):
    stop_agents(room_id)
    await cleanup_room(room_id)
    try:
        await delete_room(room_id)
    except Exception as e:
        logger.warning(f"Failed to delete LiveKit room {room_id}: {e}")
    return {"status": "stopped"}


@app.get("/health")
async def health():
    return {"status": "ok"}
