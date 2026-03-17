"use client";

import "@livekit/components-styles";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useConnectionState,
} from "@livekit/components-react";
import { ConnectionState } from "livekit-client";
import { useState } from "react";
import { AgentScreenShare } from "./AgentScreenShare";
import { UserMicControl } from "./UserMicControl";
import { AgentStatus } from "./AgentStatus";
import { Transcript } from "./Transcript";
import { ScreenShareButton } from "./ScreenShareButton";

interface CallViewProps {
  roomId: string;
  token: string;
  livekitUrl: string;
}

export function CallView({ roomId, token, livekitUrl }: CallViewProps) {
  return (
    <LiveKitRoom
      token={token}
      serverUrl={livekitUrl}
      connect={true}
      audio={true}
      video={false}
      className="h-screen w-screen"
    >
      <RoomContent roomId={roomId} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

function RoomContent({ roomId }: { roomId: string }) {
  const connectionState = useConnectionState();
  const [chatVisible, setChatVisible] = useState(true);

  if (connectionState === ConnectionState.Connecting) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="animate-spin h-8 w-8 border-2 border-[var(--accent)] border-t-transparent rounded-full mx-auto" />
          <p className="text-neutral-400">Connecting to demo room...</p>
        </div>
      </div>
    );
  }

  if (connectionState === ConnectionState.Disconnected) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-neutral-400">Disconnected from the call.</p>
          <a href="/" className="text-[var(--accent)] underline">
            Start a new demo
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Agent status bar */}
      <AgentStatus roomId={roomId} />

      {/* Main area: screen share + chat side panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Screen share */}
        <div className="flex-1 relative overflow-hidden bg-black">
          <AgentScreenShare />

          {/* Toggle chat button */}
          <button
            onClick={() => setChatVisible(!chatVisible)}
            className="absolute top-3 right-3 z-10 px-3 py-1.5 bg-neutral-800/80 hover:bg-neutral-700/80 text-neutral-300 text-sm rounded-md backdrop-blur-sm border border-neutral-700 transition-colors"
          >
            {chatVisible ? "Hide Chat" : "Show Chat"}
          </button>
        </div>

        {/* Chat side panel */}
        {chatVisible && (
          <div className="w-80 flex flex-col bg-neutral-900 border-l border-neutral-800">
            <div className="px-4 py-3 border-b border-neutral-800 text-sm font-medium text-neutral-400">
              Chat
            </div>
            <div className="flex-1 overflow-hidden px-4 py-3">
              <Transcript />
            </div>
          </div>
        )}
      </div>

      {/* Bottom bar: mic + screen share controls */}
      <div className="flex items-center justify-center gap-4 p-4 bg-neutral-900 border-t border-neutral-800">
        <UserMicControl />
        <ScreenShareButton />
      </div>
    </div>
  );
}
