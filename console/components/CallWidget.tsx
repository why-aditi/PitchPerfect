"use client";

import { useEffect, useRef, useState } from "react";
import type { IAgoraRTCClient, IMicrophoneAudioTrack } from "agora-rtc-sdk-ng";
import { startCall, stopCall } from "@/lib/api";
import type { CallState, Session } from "@/lib/types";

const RING: Record<CallState, string> = {
  idle: "border-neutral-300",
  connecting: "border-amber-400 animate-pulse",
  listening: "border-emerald-500",
  thinking: "border-amber-400 animate-pulse",
  speaking: "border-sky-500 animate-pulse",
};

export default function CallWidget({ agentId }: { agentId: string }) {
  const [state, setState] = useState<CallState>("idle");
  const [session, setSession] = useState<Session | null>(null);
  const [muted, setMuted] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const client = useRef<IAgoraRTCClient | null>(null);
  const mic = useRef<IMicrophoneAudioTrack | null>(null);

  useEffect(() => {
    if (state === "idle") return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [state]);

  async function join() {
    setError(null);
    setState("connecting");
    try {
      const s = await startCall(agentId);
      setSession(s);

      const AgoraRTC = (await import("agora-rtc-sdk-ng")).default;
      const c = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
      client.current = c;
      await c.join(s.app_id, s.channel, s.rtc_token, Number(s.uid));

      c.on("user-published", async (user, media) => {
        await c.subscribe(user, media);
        if (media === "audio") user.audioTrack?.play();
      });

      // Speaking indicator for both parties — this is how a viewer sees barge-in happen.
      c.enableAudioVolumeIndicator();
      c.on("volume-indicator", (volumes) => {
        const agent = volumes.find((v) => String(v.uid) === s.agent_rtc_uid);
        setState(agent && agent.level > 5 ? "speaking" : "listening");
      });

      mic.current = await AgoraRTC.createMicrophoneAudioTrack();
      await c.publish([mic.current]);
      setState("listening");
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not start the call");
      setState("idle");
    }
  }

  async function hangUp() {
    mic.current?.close();
    await client.current?.leave();
    if (session) await stopCall(session.session_id).catch(() => {});
    client.current = null;
    mic.current = null;
    setSession(null);
    setSeconds(0);
    setState("idle");
  }

  function toggleMute() {
    const next = !muted;
    mic.current?.setMuted(next);
    setMuted(next);
  }

  if (state === "idle") {
    return (
      <div className="text-right">
        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
        <button
          onClick={join}
          className="rounded-full bg-emerald-600 px-6 py-3 font-medium text-white shadow-lg hover:bg-emerald-700"
        >
          Talk to Sales
        </button>
      </div>
    );
  }

  const mm = Math.floor(seconds / 60);
  const ss = String(seconds % 60).padStart(2, "0");

  return (
    <div className="w-64 rounded-xl border border-neutral-200 bg-white p-5 text-center shadow-xl dark:border-neutral-700 dark:bg-neutral-900">
      <div className={`mx-auto mb-3 h-14 w-14 rounded-full border-4 ${RING[state]}`} />
      <p className="text-sm capitalize">{state}</p>
      <p className="mb-4 text-xs text-neutral-500">
        {mm}:{ss} · AI assistant, transcribed
      </p>
      <div className="flex gap-2">
        <button onClick={toggleMute} className="flex-1 rounded-md border px-3 py-2 text-sm">
          {muted ? "Unmute" : "Mute"}
        </button>
        <button onClick={hangUp} className="flex-1 rounded-md bg-red-600 px-3 py-2 text-sm text-white">
          End call
        </button>
      </div>
    </div>
  );
}
