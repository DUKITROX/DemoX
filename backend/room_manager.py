import json
import logging
from livekit.api import LiveKitAPI, AccessToken, VideoGrants, CreateRoomRequest, CreateAgentDispatchRequest, ListParticipantsRequest

from backend.config import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET

logger = logging.getLogger(__name__)


async def create_room_and_tokens(room_name: str, website_url: str = ""):
    """Create a LiveKit room and generate tokens for user and presenter agent."""
    async with LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        # Create room with website URL in metadata
        await lk.room.create_room(
            CreateRoomRequest(
                name=room_name,
                metadata=json.dumps({"url": website_url}),
                empty_timeout=300,  # 5 min timeout if empty
            )
        )

        # Explicitly dispatch agent to the room (more reliable than RoomAgentDispatch)
        dispatch = await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(agent_name="", room=room_name)
        )
        logger.info(f"Dispatched agent to room {room_name}, dispatch_id={dispatch.id}")

    # User token
    user_token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity("user")
        .with_name("User")
        .with_grants(VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        ))
        .to_jwt()
    )

    # Agent token
    agent_token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity("presenter-agent")
        .with_name("Demo Agent")
        .with_grants(VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        ))
        .to_jwt()
    )

    return {
        "room_name": room_name,
        "user_token": user_token,
        "agent_token": agent_token,
    }


async def ensure_agent_dispatched(room_name: str):
    """Check if the presenter agent is in the room; re-dispatch if not."""
    async with LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        resp = await lk.room.list_participants(ListParticipantsRequest(room=room_name))
        agent_present = any(p.identity == "presenter-agent" for p in resp.participants)
        if agent_present:
            logger.info(f"Agent already in room {room_name}, no re-dispatch needed")
            return True

        logger.warning(f"Agent NOT in room {room_name} — re-dispatching")
        dispatch = await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(agent_name="", room=room_name)
        )
        logger.info(f"Re-dispatched agent to room {room_name}, dispatch_id={dispatch.id}")
        return False


async def delete_room(room_name: str):
    """Delete a LiveKit room."""
    async with LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        await lk.room.delete_room(room_name)
