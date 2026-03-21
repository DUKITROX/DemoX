"""InstructorScreenCapture — captures frames from instructor's screen share track."""

import asyncio
import io
import logging

from PIL import Image
from livekit import rtc

logger = logging.getLogger(__name__)


class InstructorScreenCapture:
    """Subscribes to the instructor's screen share track and stores the latest frame.

    The capture loop stores raw VideoFrame references (cheap). JPEG conversion
    only happens on-demand via get_latest_screenshot().
    """

    def __init__(self):
        self._latest_frame: rtc.VideoFrame | None = None
        self._capture_task: asyncio.Task | None = None
        self._current_track: rtc.RemoteVideoTrack | None = None
        self._room: rtc.Room | None = None

    def attach_to_room(self, room: rtc.Room):
        """Listen for track subscriptions to detect instructor's screen share."""
        self._room = room

        room.on("track_subscribed", self._on_track_subscribed)
        room.on("track_unsubscribed", self._on_track_unsubscribed)

        # Check if instructor is already sharing (agent joined after share started)
        for participant in room.remote_participants.values():
            if participant.identity == "presenter-agent":
                continue
            for publication in participant.track_publications.values():
                if (
                    publication.source == rtc.TrackSource.SOURCE_SCREENSHARE
                    and publication.track is not None
                ):
                    logger.info(
                        f"Found existing screen share from {participant.identity}"
                    )
                    self._start_capture(publication.track)
                    return

    def _on_track_subscribed(
        self,
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        """Handle new track subscription — start capturing if it's a screen share."""
        if participant.identity == "presenter-agent":
            return
        if publication.source != rtc.TrackSource.SOURCE_SCREENSHARE:
            return
        if track.kind != rtc.TrackKind.KIND_VIDEO:
            return

        logger.info(f"Instructor screen share subscribed from {participant.identity}")
        self._start_capture(track)

    def _on_track_unsubscribed(
        self,
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        """Handle track unsubscription — stop capturing if it was the screen share."""
        if self._current_track and track.sid == self._current_track.sid:
            logger.info(f"Instructor screen share unsubscribed from {participant.identity}")
            self._stop_capture()

    def _start_capture(self, track: rtc.Track):
        """Start the frame capture loop for the given track."""
        self._stop_capture()
        self._current_track = track
        self._capture_task = asyncio.create_task(self._capture_loop(track))

    def _stop_capture(self):
        """Stop the current capture loop."""
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()
            self._capture_task = None
        self._current_track = None

    async def _capture_loop(self, track: rtc.Track):
        """Async iterate over video frames and store the latest one."""
        try:
            video_stream = rtc.VideoStream(track, format=rtc.VideoBufferType.RGBA)
            async for frame_event in video_stream:
                self._latest_frame = frame_event.frame
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Instructor capture loop error: {e}")

    @property
    def is_active(self) -> bool:
        """True if currently capturing from instructor's screen share."""
        return self._current_track is not None and self._capture_task is not None

    def get_latest_screenshot(
        self, width: int = 640, height: int = 360, quality: int = 50
    ) -> bytes | None:
        """Convert the latest raw frame to JPEG on demand.

        Returns JPEG bytes or None if no frame is available (instructor not sharing).
        """
        if self._latest_frame is None:
            return None

        try:
            frame = self._latest_frame
            img = Image.frombytes(
                "RGBA", (frame.width, frame.height), frame.data
            )
            if img.size != (width, height):
                img = img.resize((width, height))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=quality)
            return buf.getvalue()
        except Exception as e:
            logger.warning(f"Screenshot conversion failed: {e}")
            return None

    def stop(self):
        """Stop capturing and clean up."""
        self._stop_capture()
        self._latest_frame = None
        if self._room:
            try:
                self._room.off("track_subscribed", self._on_track_subscribed)
                self._room.off("track_unsubscribed", self._on_track_unsubscribed)
            except Exception:
                pass
            self._room = None
