"use client";

import { useLocalParticipant } from "@livekit/components-react";

export function ScreenShareButton() {
  const { localParticipant, isScreenShareEnabled } = useLocalParticipant();

  const toggleScreenShare = () => {
    localParticipant.setScreenShareEnabled(!isScreenShareEnabled);
  };

  return (
    <button
      onClick={toggleScreenShare}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
        isScreenShareEnabled
          ? "bg-green-600 text-white"
          : "bg-neutral-700 text-neutral-300 hover:bg-neutral-600"
      }`}
    >
      <ScreenShareIcon />
      <span>{isScreenShareEnabled ? "Stop Sharing" : "Share Screen"}</span>
    </button>
  );
}

function ScreenShareIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  );
}
