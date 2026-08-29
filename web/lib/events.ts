import type { RtmEvent } from "./types";

type Handler = (e: RtmEvent) => void;

/**
 * Dashboard event source. Today: a window hook so the UI can be built and demoed
 * before the backend publishes (PRD 6.2). Swap the body for an RTM subscribe on
 * `<channel>-events` — the handler signature does not change.
 */
export function subscribe(handler: Handler): () => void {
  const fn = (e: Event) => handler((e as CustomEvent<RtmEvent>).detail);
  window.addEventListener("pitchpilot-event", fn);
  (window as unknown as { emit: (e: RtmEvent) => void }).emit = (e) =>
    window.dispatchEvent(new CustomEvent("pitchpilot-event", { detail: e }));
  return () => window.removeEventListener("pitchpilot-event", fn);
}
