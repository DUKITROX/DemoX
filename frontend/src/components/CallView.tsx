"use client";

import "@livekit/components-styles";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useConnectionState,
  useRoomContext,
} from "@livekit/components-react";
import { ConnectionState } from "livekit-client";
import { useState, useCallback } from "react";
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

interface ChatMessage {
  id: string;
  text: string;
  timestamp: number;
  speaker: "You";
}

function ChatInput({ onMessageSent }: { onMessageSent: (msg: ChatMessage) => void }) {
  const room = useRoomContext();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  const handleSend = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;

    setSending(true);
    try {
      await room.localParticipant.sendText(trimmed, { topic: "lk.chat" });
      onMessageSent({
        id: `chat-${Date.now()}`,
        text: trimmed,
        timestamp: Date.now(),
        speaker: "You",
      });
      setText("");
    } catch (e) {
      console.error("Failed to send chat message:", e);
    } finally {
      setSending(false);
    }
  }, [text, sending, room, onMessageSent]);

  return (
    <div className="flex gap-2 px-4 py-3 border-t border-neutral-800">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") handleSend(); }}
        placeholder="Type a message..."
        disabled={sending}
        className="flex-1 bg-neutral-800 text-neutral-200 text-sm rounded-md px-3 py-2 border border-neutral-700 focus:outline-none focus:border-[var(--accent)] placeholder-neutral-500"
      />
      <button
        onClick={handleSend}
        disabled={sending || !text.trim()}
        className="px-3 py-2 bg-[var(--accent)] text-white text-sm rounded-md hover:opacity-90 disabled:opacity-40 transition-opacity"
      >
        Send
      </button>
    </div>
  );
}

function RoomContent({ roomId }: { roomId: string }) {
  const connectionState = useConnectionState();
  const [chatVisible, setChatVisible] = useState(true);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const handleMessageSent = useCallback((msg: ChatMessage) => {
    setChatMessages((prev) => [...prev, msg]);
  }, []);

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
              <Transcript chatMessages={chatMessages} />
            </div>
            <ChatInput onMessageSent={handleMessageSent} />
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
