import os
import logging
from typing import Optional

import httpx

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "TxGEqnHWrfWFTfGW9XjX")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

TTS_ENABLED = bool(ELEVENLABS_API_KEY)

if not TTS_ENABLED:
    logger.warning("ELEVENLABS_API_KEY not set - TTS disabled, text-only mode")

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
    return _client


async def generate_speech(text: str) -> Optional[bytes]:
    """
    Call ElevenLabs streaming TTS API and return complete MP3 bytes.
    Returns None if TTS is disabled or on any error.
    """
    if not TTS_ENABLED:
        return None

    if not text or not text.strip():
        return None

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.15,
            "use_speaker_boost": True,
        },
        "output_format": "mp3_44100_128",
    }

    try:
        client = _get_client()
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        audio_bytes = response.content
        logger.info(f"TTS generated {len(audio_bytes)} bytes for: {text[:50]}...")
        return audio_bytes
    except httpx.HTTPStatusError as e:
        logger.error(f"ElevenLabs API error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"TTS generation failed: {type(e).__name__}: {e}")
        return None
