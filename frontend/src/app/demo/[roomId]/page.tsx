"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CallView } from "@/components/CallView";

export default function DemoRoom() {
  const params = useParams();
  const roomId = params.roomId as string;
  const [token, setToken] = useState<string | null>(null);
  const [livekitUrl, setLivekitUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const storedToken = sessionStorage.getItem(`token:${roomId}`);
    const storedUrl = sessionStorage.getItem("livekit_url");

    if (!storedToken || !storedUrl) {
      setError("No session found. Please start a new demo from the homepage.");
      return;
    }

    setToken(storedToken);
    setLivekitUrl(storedUrl);
  }, [roomId]);

  if (error) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-red-400">{error}</p>
          <a href="/" className="text-[var(--accent)] underline">
            Go to homepage
          </a>
        </div>
      </div>
    );
  }

  if (!token || !livekitUrl) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-[var(--accent)] border-t-transparent rounded-full" />
      </div>
    );
  }

  return <CallView roomId={roomId} token={token} livekitUrl={livekitUrl} />;
}
