/**
 * Agora Conversational AI transcripts.
 *
 * PRD 6.2 is explicit that transcripts do not travel on our event stream: the engine
 * delivers them over the RTC data channel to whoever is in the channel, and the client
 * renders them. That makes this file the only place transcripts are decoded, and it is
 * deliberately tolerant — the engine has shipped more than one wire shape.
 *
 * Two shapes are handled:
 *   1. a UTF-8 JSON object, one message per `stream-message`
 *   2. a chunked envelope, `msg_id|part_index|total_parts|base64(part)`, for payloads
 *      larger than a single data-stream frame
 *
 * Anything that parses to neither is dropped rather than thrown: a malformed frame must
 * not take the live view down mid-demo.
 */

export type TranscriptLine = {
  /** Stable across the partials of one turn, so a partial replaces rather than appends. */
  id: string;
  role: "agent" | "prospect";
  text: string;
  /** False while the line is still being spoken or still being recognised. */
  final: boolean;
  ts: number;
};

type Chunk = { total: number; parts: Map<number, string> };

const decoder = new TextDecoder();

export class TranscriptDecoder {
  private pending = new Map<string, Chunk>();

  /** Returns the lines a frame completed. Usually one; empty while a chunk is partial. */
  push(payload: Uint8Array | ArrayBuffer | string): TranscriptLine[] {
    const raw =
      typeof payload === "string"
        ? payload
        : decoder.decode(payload instanceof Uint8Array ? payload : new Uint8Array(payload));

    const whole = this.reassemble(raw);
    if (whole === null) return [];

    const line = this.toLine(whole);
    return line ? [line] : [];
  }

  /** Chunked frames carry an ASCII header; plain frames are returned as-is. */
  private reassemble(raw: string): string | null {
    const header = raw.match(/^([^|]+)\|(\d+)\|(\d+)\|/);
    if (!header) return raw;

    const [, id, indexText, totalText] = header;
    const index = Number(indexText);
    const total = Number(totalText);
    const body = raw.slice(header[0].length);

    const chunk = this.pending.get(id) ?? { total, parts: new Map<number, string>() };
    chunk.parts.set(index, body);
    this.pending.set(id, chunk);
    if (chunk.parts.size < chunk.total) return null;

    this.pending.delete(id);
    const joined = Array.from({ length: chunk.total }, (_, i) => chunk.parts.get(i) ?? "").join("");
    try {
      // Chunk bodies are base64; a frame that was merely split on a `|` in its text is not.
      return decoder.decode(Uint8Array.from(atob(joined), (c) => c.charCodeAt(0)));
    } catch {
      return joined;
    }
  }

  private toLine(text: string): TranscriptLine | null {
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(text) as Record<string, unknown>;
    } catch {
      return null;
    }

    const object = String(message.object ?? "");
    if (!object.includes("transcription")) return null; // interrupts, metrics, errors

    const body = String(message.text ?? "").trim();
    if (!body) return null;

    const role: TranscriptLine["role"] = object.startsWith("user") ? "prospect" : "agent";
    const turn = message.turn_id ?? message.turn_seq_id ?? 0;

    return {
      id: `${role}-${turn}`,
      role,
      text: body,
      // turn_status 0 means in progress; some builds only send `final`.
      final: message.final === true || message.turn_status === 2,
      ts: Date.now(),
    };
  }
}

/** Applies a decoded line to a list, replacing the partial for the same turn. */
export function applyLine(lines: TranscriptLine[], line: TranscriptLine): TranscriptLine[] {
  const at = lines.findIndex((l) => l.id === line.id);
  if (at === -1) return [...lines, line];
  const next = [...lines];
  next[at] = line;
  return next;
}
