"use client";

import { useTracks, VideoTrack } from "@livekit/components-react";
import { Track } from "livekit-client";
import { useMemo } from "react";

export function AgentScreenShare() {
  const tracks = useTracks([Track.Source.ScreenShare]);

  const screenTrackRef = useMemo(
    () => tracks.find((t) => t.participant.identity === "presenter-agent"),
    // Stabilize on trackSid so the reference only changes when the actual track changes,
    // not on every room re-render (which would cause detach/reattach → black flash).
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      tracks.find((t) => t.participant.identity === "presenter-agent")
        ?.publication.trackSid,
    ]
  );

  if (!screenTrackRef) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="animate-pulse h-6 w-6 bg-[var(--accent)] rounded-full mx-auto" />
          <p className="text-neutral-400">
            Waiting for the agent to start sharing its screen...
          </p>
        </div>
      </div>
    );
  }

  return (
    <VideoTrack
      trackRef={screenTrackRef}
      className="w-full h-full object-contain"
      muted
    />
  );
}
