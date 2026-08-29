import type { RtmEvent } from "./types";

type Handler = (e: RtmEvent) => void;

/**
 * Dashboard event source: the backend's SSE stream, carrying the PRD 6.2 envelope.
 * EventSource reconnects on its own, so there is no retry logic here.
 *
 * window.emit({type, session_id, ts, data}) still works from the console for
 * demoing the UI with no backend running.
 */
export function subscribe(handler: Handler): () => void {
  const source = new EventSource("/api/events");
  source.onmessage = (e) => handler(JSON.parse(e.data) as RtmEvent);

  const manual = (e: Event) => handler((e as CustomEvent<RtmEvent>).detail);
  window.addEventListener("pitchpilot-event", manual);
  (window as unknown as { emit: (e: RtmEvent) => void }).emit = (e) =>
    window.dispatchEvent(new CustomEvent("pitchpilot-event", { detail: e }));

  return () => {
    source.close();
    window.removeEventListener("pitchpilot-event", manual);
  };
}
