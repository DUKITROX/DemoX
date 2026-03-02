"use client";

import { useLocalParticipant } from "@livekit/components-react";

export function UserMicControl() {
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();

  const toggleMic = () => {
    localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled);
  };

  return (
    <button
      onClick={toggleMic}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
        isMicrophoneEnabled
          ? "bg-[var(--accent)] text-white"
          : "bg-neutral-700 text-neutral-300 hover:bg-neutral-600"
      }`}
    >
      {isMicrophoneEnabled ? (
        <>
          <MicOnIcon />
          <span>Mute</span>
        </>
      ) : (
        <>
          <MicOffIcon />
          <span>Unmute</span>
        </>
      )}
    </button>
  );
}

function MicOnIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function MicOffIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="1" y1="1" x2="23" y2="23" />
      <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
      <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2c0 .76-.12 1.5-.35 2.18" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}
