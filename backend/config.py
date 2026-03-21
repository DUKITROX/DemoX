import os
from dotenv import load_dotenv

load_dotenv()

LIVEKIT_URL = os.environ["LIVEKIT_URL"]
LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# OpenRouter LLM config (used by all LLM call sites)
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
LLM_MODEL = os.environ.get("LLM_MODEL", "anthropic/claude-haiku-4.5")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Optional site-scoped login credentials (hostname only, e.g. "example.com")
LOGIN_URL = os.environ.get("LOGIN_URL")
LOGIN_EMAIL = os.environ.get("LOGIN_EMAIL")
LOGIN_PASSWORD = os.environ.get("LOGIN_PASSWORD")

# Fast demo mode: skip Student Mode, go straight to Demo Expert with existing roadmap
FAST_DEMO = os.environ.get("FAST_DEMO", "").lower() in ("1", "true", "yes")
