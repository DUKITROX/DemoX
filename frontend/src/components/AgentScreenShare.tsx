"use client";

import { useTracks, VideoTrack } from "@livekit/components-react";
import { Track } from "livekit-client";
import { useMemo } from "react";

export function AgentScreenShare() {
  const tracks = useTracks([Track.Source.ScreenShare]);

  // Priority: show agent's screen share (Demo Expert Mode), otherwise show instructor's
  const agentTrack = useMemo(
    () => tracks.find((t) => t.participant.identity === "presenter-agent"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      tracks.find((t) => t.participant.identity === "presenter-agent")
        ?.publication.trackSid,
    ]
  );

  const instructorTrack = useMemo(
    () => tracks.find((t) => t.participant.identity !== "presenter-agent"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      tracks.find((t) => t.participant.identity !== "presenter-agent")
        ?.publication.trackSid,
    ]
  );

  const screenTrackRef = agentTrack || instructorTrack;

  if (!screenTrackRef) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="animate-pulse h-6 w-6 bg-[var(--accent)] rounded-full mx-auto" />
          <p className="text-neutral-400">
            Share your screen to start teaching the agent
          </p>
        </div>
      </div>
    );
  }

  const isAgentSharing = screenTrackRef === agentTrack;

  return (
    <div className="absolute inset-0">
      <VideoTrack
        trackRef={screenTrackRef}
        className="w-full h-full"
        style={{ objectFit: "contain", objectPosition: "center" }}
        muted
      />
      {/* Label showing whose screen is being displayed */}
      <div className="absolute bottom-3 left-3 px-2 py-1 bg-black/60 text-neutral-300 text-xs rounded backdrop-blur-sm">
        {isAgentSharing ? "Agent's screen" : "Your screen"}
      </div>
    </div>
  );
}
