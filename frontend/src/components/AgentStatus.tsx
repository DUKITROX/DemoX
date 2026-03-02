"use client";

import { useEffect, useState } from "react";

interface AgentStatusProps {
  roomId: string;
}

interface StatusData {
  status: string;
  research_ready: boolean;
}

export function AgentStatus({ roomId }: AgentStatusProps) {
  const [status, setStatus] = useState<StatusData | null>(null);

  useEffect(() => {
    let active = true;

    async function poll() {
      try {
        const res = await fetch(`/api/demo/${roomId}/status`);
        if (res.ok && active) {
          setStatus(await res.json());
        }
      } catch {
        // ignore fetch errors during polling
      }
    }

    poll();
    const interval = setInterval(poll, 3000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [roomId]);

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-neutral-900 border-b border-neutral-800 text-sm">
      <div className="flex items-center gap-2">
        <div
          className={`h-2 w-2 rounded-full ${
            status?.status === "active" ? "bg-green-500" : "bg-yellow-500 animate-pulse"
          }`}
        />
        <span className="text-neutral-400">
          {status?.status === "active" ? "Demo Active" : "Setting up..."}
        </span>
      </div>

      <div className="h-4 w-px bg-neutral-700" />

      <div className="flex items-center gap-2">
        <span className="text-neutral-500">Research:</span>
        <span className={status?.research_ready ? "text-green-400" : "text-yellow-400"}>
          {status?.research_ready ? "Ready" : "Analyzing..."}
        </span>
      </div>

      <div className="flex-1" />

      <span className="text-neutral-600 text-xs">Room: {roomId}</span>
    </div>
  );
}
