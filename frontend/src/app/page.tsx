"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  async function startDemo(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/demo/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });

      if (!res.ok) {
        throw new Error("Failed to start demo");
      }

      const data = await res.json();

      // Store credentials for the demo room
      sessionStorage.setItem(`token:${data.room_id}`, data.user_token);
      sessionStorage.setItem("livekit_url", data.livekit_url);

      router.push(`/demo/${data.room_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="max-w-2xl w-full text-center space-y-8">
        <div className="space-y-4">
          <h1 className="text-5xl font-bold tracking-tight">
            Demo<span className="text-[var(--accent)]">X</span>
          </h1>
          <p className="text-xl text-neutral-400">
            Paste any website URL and get an instant, live AI-powered demo.
          </p>
          <p className="text-sm text-neutral-500">
            An AI agent will join a call with you, share its screen, and walk
            you through the website in real time.
          </p>
        </div>

        <form onSubmit={startDemo} className="space-y-4">
          <div className="flex gap-3">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://stripe.com"
              required
              className="flex-1 px-4 py-3 rounded-lg bg-neutral-900 border border-neutral-700
                         text-white placeholder-neutral-500 focus:outline-none focus:border-[var(--accent)]
                         text-lg"
            />
            <button
              type="submit"
              disabled={loading || !url.trim()}
              className="px-6 py-3 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)]
                         text-white font-semibold text-lg transition-colors disabled:opacity-50
                         disabled:cursor-not-allowed whitespace-nowrap"
            >
              {loading ? "Starting..." : "Start Demo →"}
            </button>
          </div>

          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}
        </form>

        <div className="grid grid-cols-3 gap-6 text-sm text-neutral-500 pt-8">
          <div>
            <div className="text-2xl mb-2">🎙️</div>
            <div className="font-medium text-neutral-300">Voice Interaction</div>
            <div>Talk naturally with the AI agent</div>
          </div>
          <div>
            <div className="text-2xl mb-2">🖥️</div>
            <div className="font-medium text-neutral-300">Live Screen Share</div>
            <div>Watch the agent navigate in real time</div>
          </div>
          <div>
            <div className="text-2xl mb-2">🧠</div>
            <div className="font-medium text-neutral-300">Deep Research</div>
            <div>Background AI analyzes the whole site</div>
          </div>
        </div>
      </div>
    </main>
  );
}
