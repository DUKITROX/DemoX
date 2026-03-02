"use client";

import {
  useTrackTranscription,
  useLocalParticipant,
  useRemoteParticipants,
  useTracks,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import { useEffect, useRef } from "react";

export function Transcript() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const localParticipant = useLocalParticipant();
  const remoteParticipants = useRemoteParticipants();
  const tracks = useTracks([Track.Source.Microphone]);

  // Find the agent's audio track for transcription
  const agentTrack = tracks.find(
    (t) => t.participant.identity === "presenter-agent"
  );
  const userTrack = tracks.find(
    (t) => t.participant.identity === "user"
  );

  const agentTranscription = useTrackTranscription(agentTrack);
  const userTranscription = useTrackTranscription(userTrack);

  // Combine and sort segments
  const allSegments = [
    ...agentTranscription.segments.map((s) => ({ ...s, speaker: "Agent" })),
    ...userTranscription.segments.map((s) => ({ ...s, speaker: "You" })),
  ].sort((a, b) => a.firstReceivedTime - b.firstReceivedTime);

  // Keep only last 10 segments
  const recentSegments = allSegments.slice(-10);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [recentSegments.length]);

  if (recentSegments.length === 0) {
    return (
      <div className="text-neutral-600 text-sm italic">
        Waiting for conversation to start...
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="overflow-y-auto space-y-2 text-sm h-full">
      {recentSegments.map((segment, i) => (
        <div key={segment.id || i}>
          <span
            className={
              segment.speaker === "Agent"
                ? "text-[var(--accent)] font-medium"
                : "text-blue-400 font-medium"
            }
          >
            {segment.speaker}:
          </span>{" "}
          <span className="text-neutral-300">{segment.text}</span>
        </div>
      ))}
    </div>
  );
}
