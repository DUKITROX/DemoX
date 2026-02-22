import os
import logging
from typing import Optional

import httpx

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_STT_MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2")

STT_ENABLED = bool(ELEVENLABS_API_KEY)

if not STT_ENABLED:
    logger.warning("ELEVENLABS_API_KEY not set - STT disabled")

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
    return _client


async def transcribe_audio(audio_bytes: bytes, content_type: str = "audio/webm") -> Optional[str]:
    """
    Call ElevenLabs Speech-to-Text API and return the transcript text.
    Returns None if STT is disabled or on any error.
    """
    if not STT_ENABLED:
        return None

    if not audio_bytes:
        return None

    # Map content type to file extension for the multipart upload
    ext_map = {
        "audio/webm": "audio.webm",
        "audio/ogg": "audio.ogg",
        "audio/mp4": "audio.mp4",
        "audio/wav": "audio.wav",
        "audio/mpeg": "audio.mp3",
    }
    filename = ext_map.get(content_type, "audio.webm")

    url = "https://api.elevenlabs.io/v1/speech-to-text"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
    }

    try:
        client = _get_client()
        response = await client.post(
            url,
            headers=headers,
            data={"model_id": ELEVENLABS_STT_MODEL},
            files={"file": (filename, audio_bytes, content_type)},
        )
        response.raise_for_status()
        result = response.json()
        transcript = result.get("text", "").strip()
        logger.info(f"STT transcribed {len(audio_bytes)} bytes -> '{transcript[:80]}...'")
        return transcript if transcript else None
    except httpx.HTTPStatusError as e:
        logger.error(f"ElevenLabs STT API error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"STT transcription failed: {type(e).__name__}: {e}")
        return None
