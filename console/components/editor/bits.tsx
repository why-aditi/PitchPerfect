"use client";

/**
 * Shared pieces of the agent editor. Every tab needs a list of short strings and most of
 * them want a JSON escape hatch, so those live here rather than in five near-copies that
 * drift apart the first time one of them gets a fix.
 */
import { useState, type ReactNode } from "react";
import { Button, Input, Textarea, cx } from "@/components/ui";

/* ---------------------------------------------------------------- icons */
/* Hairline strokes at 14px so a row of controls reads as chrome, not as content. */

const svg = "h-3.5 w-3.5";

export const IconPlus = () => (
  <svg className={svg} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
    <path d="M7 2.5v9M2.5 7h9" />
  </svg>
);

export const IconTrash = () => (
  <svg className={svg} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2.5 3.5h9M5.5 3.5V2.2h3v1.3M3.6 3.5l.5 8h5.8l.5-8" />
  </svg>
);

export const IconCopy = () => (
  <svg className={svg} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
    <rect x="4.6" y="4.6" width="7" height="7" rx="1.4" />
    <path d="M9.4 2.4H2.9a.5.5 0 0 0-.5.5v6.5" />
  </svg>
);

export const IconCheck = () => (
  <svg className={svg} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2.6 7.4l3 3 5.8-6.8" />
  </svg>
);

export const IconUp = () => (
  <svg className={svg} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3.5 8.5L7 5l3.5 3.5" />
  </svg>
);

export const IconDown = () => (
  <svg className={svg} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3.5 5.5L7 9l3.5-3.5" />
  </svg>
);

export const IconChevron = ({ open }: { open: boolean }) => (
  <svg
    className={cx(svg, "transition-transform", open && "rotate-90")}
    viewBox="0 0 14 14"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M5.5 3.5L9 7l-3.5 3.5" />
  </svg>
);

export const IconDuplicate = () => (
  <svg className={svg} viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
    <rect x="5" y="5" width="6.6" height="6.6" rx="1.3" />
    <path d="M9 2.6H3.1a.5.5 0 0 0-.5.5V9" />
  </svg>
);

/* ---------------------------------------------------------------- controls */

export function IconButton({
  label,
  onClick,
  disabled,
  tone = "quiet",
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: "quiet" | "danger";
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-35",
        tone === "danger"
          ? "text-faint hover:border-escalate/50 hover:text-escalate"
          : "text-faint hover:border-brand/50 hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

export function Hint({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-faint">{children}</p>;
}

/** Inline and non-blocking: the data is suspect, but the operator may still know better. */
export function Warn({ children }: { children: ReactNode }) {
  return (
    <p className="flex gap-2 rounded-lg border border-thinking/30 bg-thinking/5 px-3 py-2 text-xs text-thinking">
      <span aria-hidden className="mt-[5px] block h-1.5 w-1.5 shrink-0 rounded-full bg-thinking" />
      <span className="leading-relaxed">{children}</span>
    </p>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-escalate/30 bg-escalate/5 px-3 py-2 font-mono text-xs leading-relaxed text-escalate">
      {children}
    </p>
  );
}

/** A titled block with an optional action in the corner: the unit every tab is built from. */
export function Group({
  title,
  action,
  children,
}: {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex min-h-8 items-center justify-between gap-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/* ---------------------------------------------------------------- list editor */

export function ListEditor({
  items,
  onChange,
  placeholder,
  addLabel = "Add item",
  ordered = false,
  emptyNote,
}: {
  items: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  addLabel?: string;
  /** Ordered lists get rank numbers and move controls; the goal hierarchy is read in order. */
  ordered?: boolean;
  emptyNote?: string;
}) {
  const set = (i: number, v: string) => onChange(items.map((it, n) => (n === i ? v : it)));
  const remove = (i: number) => onChange(items.filter((_, n) => n !== i));
  const move = (i: number, delta: number) => {
    const next = [...items];
    const [moved] = next.splice(i, 1);
    next.splice(i + delta, 0, moved);
    onChange(next);
  };

  return (
    <div className="space-y-2">
      {items.length === 0 && emptyNote && (
        <p className="rounded-lg border border-dashed border-line px-3 py-3 text-xs text-faint">
          {emptyNote}
        </p>
      )}
      {items.map((item, i) => (
        // Index keys: these rows are plain text with no identity of their own, and the
        // move controls rewrite the whole array anyway.
        <div key={i} className="flex items-center gap-2">
          {ordered && (
            <span className="w-5 shrink-0 text-right font-mono text-xs text-faint">{i + 1}</span>
          )}
          <Input value={item} placeholder={placeholder} onChange={(e) => set(i, e.target.value)} />
          {ordered && (
            <>
              <IconButton label="Move up" onClick={() => move(i, -1)} disabled={i === 0}>
                <IconUp />
              </IconButton>
              <IconButton
                label="Move down"
                onClick={() => move(i, 1)}
                disabled={i === items.length - 1}
              >
                <IconDown />
              </IconButton>
            </>
          )}
          <IconButton label="Remove" tone="danger" onClick={() => remove(i)}>
            <IconTrash />
          </IconButton>
        </div>
      ))}
      <Button
        variant="ghost"
        className="px-3 py-1.5 text-xs"
        onClick={() => onChange([...items, ""])}
      >
        <IconPlus />
        {addLabel}
      </Button>
    </div>
  );
}

/* ---------------------------------------------------------------- JSON editors */

/**
 * A JSON textarea that writes through only when the text parses *and* the caller's
 * validator accepts the shape. The editor this replaced called setConfig on every
 * keystroke that happened to be valid JSON, so a half-typed tier array could reach the
 * save button. `onApply` returns an error string to reject, or null to accept.
 */
function JsonBody({
  value,
  onApply,
  rows,
  applyLabel,
}: {
  value: unknown;
  onApply: (parsed: unknown) => string | null;
  rows: number;
  applyLabel: string;
}) {
  const serialised = JSON.stringify(value, null, 2);
  const [text, setText] = useState(serialised);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);
  const [synced, setSynced] = useState(serialised);

  // The structured controls are the primary way in, so the text follows whatever they do.
  // Adjusted during render rather than in an effect: an effect would paint the stale text
  // for a frame first, and the textarea would visibly flicker on every keystroke upstream.
  if (serialised !== synced) {
    setSynced(serialised);
    setText(serialised);
    setError(null);
  }

  const dirty = text !== serialised;

  const apply = () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "not valid JSON");
      setApplied(false);
      return;
    }
    const rejected = onApply(parsed);
    setError(rejected);
    setApplied(!rejected);
  };

  return (
    <div className="space-y-2">
      <Textarea
        rows={rows}
        spellCheck={false}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setApplied(false);
        }}
        className="font-mono text-xs leading-relaxed"
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex items-center gap-2">
        <Button variant="ghost" className="px-3 py-1.5 text-xs" onClick={apply} disabled={!dirty}>
          {applyLabel}
        </Button>
        <Button
          variant="quiet"
          className="px-2 py-1.5 text-xs"
          onClick={() => {
            setText(serialised);
            setError(null);
            setApplied(false);
          }}
          disabled={!dirty}
        >
          Discard edits
        </Button>
        {applied && !dirty && (
          <span className="flex items-center gap-1 text-xs text-listening">
            <IconCheck />
            applied
          </span>
        )}
      </div>
    </div>
  );
}

/** Collapsed by default: the power-user path, not the one the tab is designed around. */
export function RawJson({
  label,
  value,
  onApply,
  rows = 14,
}: {
  label: string;
  value: unknown;
  onApply: (parsed: unknown) => string | null;
  rows?: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-line-soft">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left font-mono text-[11px] uppercase tracking-[0.12em] text-faint transition-colors hover:text-ink"
      >
        <IconChevron open={open} />
        {label}
      </button>
      {open && (
        <div className="border-t border-line-soft p-3">
          <JsonBody value={value} onApply={onApply} rows={rows} applyLabel="Apply JSON" />
        </div>
      )}
    </div>
  );
}

/** Always-open variant for a field whose only sane editor is JSON, like tts_params. */
export function JsonField({
  value,
  onApply,
  rows = 5,
}: {
  value: unknown;
  onApply: (parsed: unknown) => string | null;
  rows?: number;
}) {
  return <JsonBody value={value} onApply={onApply} rows={rows} applyLabel="Apply" />;
}

/* ---------------------------------------------------------------- copy */

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      variant="ghost"
      className="px-3 py-1.5 text-xs"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
        } catch {
          return; // Clipboard access is permission-gated; a dead button beats a red error.
        }
        setDone(true);
        setTimeout(() => setDone(false), 1600);
      }}
    >
      {done ? <IconCheck /> : <IconCopy />}
      {done ? "Copied" : label}
    </Button>
  );
}
