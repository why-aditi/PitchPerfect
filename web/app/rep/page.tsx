"use client";

import { useEffect, useState } from "react";
import { subscribe } from "@/lib/events";
import { startCall } from "@/lib/api";
import type { RtmEvent } from "@/lib/types";

type Escalation = { reason: string; summary: string; channel: string; ts: number };

export default function RepView() {
  const [queue, setQueue] = useState<Escalation[]>([]);
  const [joined, setJoined] = useState<string | null>(null);

  useEffect(
    () =>
      subscribe((e: RtmEvent) => {
        if (e.type === "escalation") setQueue((q) => [{ ...e.data, ts: e.ts }, ...q]);
      }),
    [],
  );

  // Joins the same RTC channel the prospect and agent are already in (PRD 10).
  async function join(channel: string) {
    const s = await startCall("rep");
    const AgoraRTC = (await import("agora-rtc-sdk-ng")).default;
    const client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
    await client.join(s.app_id, channel, s.rtc_token, Number(s.uid));
    client.on("user-published", async (user, media) => {
      await client.subscribe(user, media);
      if (media === "audio") user.audioTrack?.play();
    });
    await client.publish([await AgoraRTC.createMicrophoneAudioTrack()]);
    setJoined(channel);
  }

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold">Escalations</h1>
      {queue.length === 0 && (
        <p className="mt-4 text-sm text-neutral-500">Waiting for escalations…</p>
      )}
      <ul className="mt-6 space-y-4">
        {queue.map((e) => (
          <li key={e.ts} className="rounded-xl border border-neutral-200 p-5 dark:border-neutral-700">
            <p className="text-xs uppercase tracking-wide text-neutral-500">{e.channel}</p>
            <pre className="mt-2 whitespace-pre-wrap font-mono text-sm">{e.summary}</pre>
            <button
              onClick={() => join(e.channel)}
              disabled={joined === e.channel}
              className="mt-4 rounded-md bg-emerald-600 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {joined === e.channel ? "In call" : "Join call"}
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}
