"""InstructorScreenWatcher — watches instructor's screen share and syncs agent's Playwright browser.

Captures frames from the instructor's LiveKit screen share track every ~3 seconds,
analyzes them with Claude Haiku (vision) to detect the current page/URL, and navigates
the agent's Playwright browser to match for full DOM access.
"""

import asyncio
import base64
import io
import json
import logging
import os
import time

import anthropic
from PIL import Image
from livekit import rtc

logger = logging.getLogger(__name__)

ANALYSIS_INTERVAL = 3.0  # seconds between vision analyses
FRAME_MAX_WIDTH = 1024   # resize frames before sending to vision API
FRAME_MAX_HEIGHT = 768


class InstructorScreenWatcher:
    """Watches instructor's screen share and mirrors navigation in Playwright."""

    def __init__(self, room: rtc.Room, screen_share, base_url: str):
        self.room = room
        self.screen_share = screen_share  # BrowserScreenShare instance
        self.base_url = base_url.rstrip("/")
        self._current_page: str | None = None
        self._latest_description: str | None = None
        self._video_stream: rtc.VideoStream | None = None
        self._watch_task: asyncio.Task | None = None
        self._running = False
        self._client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    async def start(self):
        """Start listening for instructor's screen share track."""
        self._running = True
        self.room.on("track_subscribed", self._on_track_subscribed)
        self.room.on("track_unsubscribed", self._on_track_unsubscribed)

        # Check if instructor is already sharing (joined after them)
        for participant in self.room.remote_participants.values():
            for pub in participant.track_publications.values():
                if (
                    pub.source == rtc.TrackSource.SOURCE_SCREENSHARE
                    and pub.track is not None
                    and pub.subscribed
                ):
                    logger.info(f"Found existing screen share from {participant.identity}")
                    self._start_watching(pub.track)
                    break

    async def stop(self):
        """Stop watching instructor's screen share."""
        self._running = False
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        self._watch_task = None
        self._video_stream = None

    @property
    def current_page(self) -> str | None:
        """The currently detected page path (e.g., '/pricing')."""
        return self._current_page

    @property
    def latest_description(self) -> str | None:
        """The latest vision analysis description of the instructor's screen."""
        return self._latest_description

    @property
    def is_watching(self) -> bool:
        """Whether the watcher is actively receiving frames."""
        return self._watch_task is not None and not self._watch_task.done()

    def _on_track_subscribed(self, track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        """Called when a remote track is subscribed."""
        if not self._running:
            return
        if publication.source == rtc.TrackSource.SOURCE_SCREENSHARE:
            logger.info(f"Instructor {participant.identity} started screen sharing")
            self._start_watching(track)

    def _on_track_unsubscribed(self, track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        """Called when a remote track is unsubscribed."""
        if publication.source == rtc.TrackSource.SOURCE_SCREENSHARE:
            logger.info(f"Instructor {participant.identity} stopped screen sharing")
            if self._watch_task and not self._watch_task.done():
                self._watch_task.cancel()
            self._watch_task = None
            self._video_stream = None

    def _start_watching(self, track: rtc.Track):
        """Begin capturing frames from the given video track."""
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
        self._video_stream = rtc.VideoStream(track)
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def _watch_loop(self):
        """Capture a frame every ~3s, analyze with vision, navigate if page changed."""
        last_analysis_time = 0.0
        try:
            async for event in self._video_stream:
                if not self._running:
                    break
                now = time.time()
                if now - last_analysis_time < ANALYSIS_INTERVAL:
                    continue
                last_analysis_time = now

                try:
                    frame_b64 = self._frame_to_base64_jpeg(event.frame)
                    result = await self._analyze_frame(frame_b64)
                    if result:
                        url_path = result.get("url_path")
                        description = result.get("description")
                        self._latest_description = description

                        if url_path and url_path != self._current_page:
                            self._current_page = url_path
                            target_url = f"{self.base_url}{url_path}"
                            logger.info(f"Instructor navigated to {url_path} — syncing Playwright")
                            try:
                                await self.screen_share.navigate(target_url)
                            except Exception as e:
                                logger.warning(f"Failed to sync navigation to {target_url}: {e}")
                except Exception as e:
                    logger.warning(f"Frame analysis error: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Watch loop error: {e}")

    @staticmethod
    def _frame_to_base64_jpeg(frame: rtc.VideoFrame) -> str:
        """Convert a VideoFrame to a base64-encoded JPEG for the vision API."""
        # Convert frame buffer to PIL Image
        img = Image.frombytes("RGBA", (frame.width, frame.height), frame.data)
        img = img.convert("RGB")

        # Resize to save API costs
        if img.width > FRAME_MAX_WIDTH or img.height > FRAME_MAX_HEIGHT:
            img.thumbnail((FRAME_MAX_WIDTH, FRAME_MAX_HEIGHT), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    async def _analyze_frame(self, frame_b64: str) -> dict | None:
        """Send frame to Claude Haiku for page/URL detection."""
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": frame_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"You are analyzing a screenshot of a website being shown by an instructor.\n"
                                    f"The base website URL is: {self.base_url}\n\n"
                                    f"Identify:\n"
                                    f"1. The current page/section path (e.g., '/pricing', '/features', '/about', '/' for home)\n"
                                    f"2. A brief description of what's visible on the page\n\n"
                                    f"Respond with JSON only: {{\"url_path\": \"/detected/path\", \"description\": \"Brief description\"}}\n\n"
                                    f"If you cannot determine the page, respond: {{\"url_path\": null, \"description\": \"Cannot determine\"}}"
                                ),
                            },
                        ],
                    }
                ],
            )
            text = response.content[0].text.strip()
            # Parse JSON from response (handle markdown code blocks)
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            return None
