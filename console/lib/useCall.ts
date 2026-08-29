"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  IAgoraRTCClient,
  IAgoraRTCRemoteUser,
  IMicrophoneAudioTrack,
} from "agora-rtc-sdk-ng";
import { observeChannel, startCall, stopCall } from "./api";
import { applyLine, TranscriptDecoder, type TranscriptLine } from "./transcript";
import type { CallState, Session } from "./types";

/**
 * Every RTC join in the console goes through this hook.
 *
 * Three screens need a channel: the widget places the call, the rep view joins one that is
 * already running, and the live view listens to one without being heard. They differ only
 * in how the token is obtained and whether a microphone is published, so they are one hook
 * with two modes rather than three copies of the Agora lifecycle — which is what they were,
 * and the copies had already drifted.
 */
export type CallMode =
  | { kind: "call"; agentId: string; pageContext?: string; pageOrigin?: string }
  | { kind: "observe"; agentId: string; channel: string; mic: boolean };

/** Volume units are 0–100; anything under this is room noise, not speech. */
const SPEAKING = 5;
/** Prospect finished, agent has not started: that gap is the model thinking. */
const THINKING_AFTER_MS = 400;

export type Call = {
  state: CallState;
  session: Session | null;
  transcript: TranscriptLine[];
  agentSpeaking: boolean;
  prospectSpeaking: boolean;
  muted: boolean;
  seconds: number;
  error: string | null;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  toggleMute: () => void;
};

export function useCall(mode: CallMode): Call {
  const [state, setState] = useState<CallState>("idle");
  const [session, setSession] = useState<Session | null>(null);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [prospectSpeaking, setProspectSpeaking] = useState(false);
  const [muted, setMuted] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const client = useRef<IAgoraRTCClient | null>(null);
  const mic = useRef<IMicrophoneAudioTrack | null>(null);
  const decoder = useRef(new TranscriptDecoder());
  const lastProspect = useRef(0);
  // The hook re-renders on every volume tick; reading the mode from a ref keeps `start`
  // stable so effects that call it do not re-fire on each tick. The write happens after
  // paint rather than during render — `start` only ever runs from an event or an effect,
  // both of which are after the ref has caught up.
  const modeRef = useRef(mode);
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    if (state === "idle") return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [state]);

  const stop = useCallback(async () => {
    mic.current?.close();
    mic.current = null;
    const c = client.current;
    client.current = null;
    if (c) await c.leave().catch(() => {});
    if (session && modeRef.current.kind === "call") {
      await stopCall(session.session_id).catch(() => {});
    }
    decoder.current = new TranscriptDecoder();
    setSession(null);
    setSeconds(0);
    setAgentSpeaking(false);
    setProspectSpeaking(false);
    setMuted(false);
    setState("idle");
  }, [session]);

  const start = useCallback(async () => {
    if (client.current) return;
    const current = modeRef.current;
    setError(null);
    setTranscript([]);
    setState("connecting");

    try {
      const s =
        current.kind === "call"
          ? await startCall(current.agentId, current.pageContext, current.pageOrigin)
          : await observeChannel(current.agentId, current.channel);
      setSession(s);

      const AgoraRTC = (await import("agora-rtc-sdk-ng")).default;
      AgoraRTC.setLogLevel(3); // warnings and errors only; the SDK is chatty at info
      const c = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
      client.current = c;

      c.on("user-published", async (user: IAgoraRTCRemoteUser, media) => {
        await c.subscribe(user, media);
        if (media === "audio") user.audioTrack?.play();
      });

      // PRD 6.2: the engine delivers transcripts on the data channel, to the client, and
      // the backend never republishes them. This listener is that subscription.
      c.on("stream-message", (_uid: number, payload: Uint8Array) => {
        for (const line of decoder.current.push(payload)) {
          setTranscript((lines) => applyLine(lines, line));
          if (line.role === "prospect") lastProspect.current = Date.now();
        }
      });

      // Visible speaking indicator for both parties — this is how a viewer sees barge-in.
      c.enableAudioVolumeIndicator();
      c.on("volume-indicator", (volumes) => {
        const agent = volumes.find((v) => String(v.uid) === s.agent_rtc_uid);
        const others = volumes.filter((v) => String(v.uid) !== s.agent_rtc_uid);
        const agentOn = (agent?.level ?? 0) > SPEAKING;
        const humanOn = others.some((v) => v.level > SPEAKING);

        setAgentSpeaking(agentOn);
        setProspectSpeaking(humanOn);
        if (humanOn) lastProspect.current = Date.now();

        setState(
          agentOn
            ? "speaking"
            : !humanOn && Date.now() - lastProspect.current < THINKING_AFTER_MS + 1200 &&
                Date.now() - lastProspect.current > THINKING_AFTER_MS
              ? "thinking"
              : "listening",
        );
      });

      await c.join(s.app_id, s.channel, s.rtc_token, Number(s.uid));

      const wantsMic = current.kind === "call" || current.mic;
      if (wantsMic) {
        mic.current = await AgoraRTC.createMicrophoneAudioTrack();
        await c.publish([mic.current]);
      }
      setState("listening");
    } catch (e) {
      client.current?.leave().catch(() => {});
      client.current = null;
      setError(message(e));
      setState("idle");
    }
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((m) => {
      mic.current?.setMuted(!m);
      return !m;
    });
  }, []);

  // A tab closed mid-call must still leave the channel, or the engine keeps the agent up
  // until idle_timeout — which the PRD says never to rely on.
  useEffect(() => {
    return () => {
      mic.current?.close();
      client.current?.leave().catch(() => {});
      client.current = null;
    };
  }, []);

  return {
    state,
    session,
    transcript,
    agentSpeaking,
    prospectSpeaking,
    muted,
    seconds,
    error,
    start,
    stop,
    toggleMute,
  };
}

function message(e: unknown): string {
  if (e instanceof Error) {
    if (/NotAllowed|Permission/i.test(e.message)) return "Microphone permission was refused.";
    if (/403|origin/i.test(e.message)) return "This origin is not on the agent's allowed list.";
    return e.message;
  }
  return "The call could not be started.";
}

export function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
