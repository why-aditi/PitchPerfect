/**
 * Console primitives. Every screen composes these — a screen that reaches for a raw
 * `<button className="...">` is a screen that will drift from the rest by demo day.
 *
 * Tone rules the kit enforces: sentence case everywhere, one accent, and the monospace
 * face only on things that are literally identifiers (ids, channels, tool names, JSON).
 */
import type { ComponentProps, ReactNode } from "react";

export const cx = (...parts: (string | false | null | undefined)[]) =>
  parts.filter(Boolean).join(" ");

/* ---------------------------------------------------------------- buttons */

type Variant = "primary" | "ghost" | "danger" | "quiet";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-ink text-surface hover:bg-ink/85 disabled:bg-raised disabled:text-faint font-medium",
  ghost:
    "border border-line bg-panel text-ink hover:border-ink/40 disabled:hover:border-line",
  danger:
    "border border-escalate/40 text-escalate hover:bg-escalate/10 bg-transparent",
  quiet: "text-muted hover:text-ink hover:bg-raised bg-transparent",
};

export function Button({
  variant = "primary",
  className,
  ...rest
}: ComponentProps<"button"> & { variant?: Variant }) {
  return (
    <button
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 py-2 text-sm",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        VARIANT[variant],
        className,
      )}
    />
  );
}

/* ---------------------------------------------------------------- surfaces */

export function Card({ className, ...rest }: ComponentProps<"div">) {
  return (
    <div
      {...rest}
      className={cx("rounded-xl border border-line bg-panel", className)}
    />
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-sm font-medium text-muted">{children}</h2>;
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line px-6 py-10 text-center text-sm text-muted">
      {children}
    </div>
  );
}

/* ---------------------------------------------------------------- fields */

const CONTROL =
  "w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink " +
  "placeholder:text-faint outline-none transition-colors hover:border-faint focus:border-brand focus:ring-2 focus:ring-brand/20";

export function Field({
  label,
  hint,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-ink">{label}</span>
      {hint && <span className="mt-0.5 block text-xs leading-relaxed text-faint">{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

export function Input({ className, ...rest }: ComponentProps<"input">) {
  return <input {...rest} className={cx(CONTROL, className)} />;
}

export function Textarea({ className, ...rest }: ComponentProps<"textarea">) {
  return <textarea {...rest} className={cx(CONTROL, "resize-y leading-relaxed", className)} />;
}

export function Select({ className, ...rest }: ComponentProps<"select">) {
  return <select {...rest} className={cx(CONTROL, "appearance-none", className)} />;
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-4 rounded-lg border border-line bg-panel px-3.5 py-3 text-left transition-colors hover:border-faint"
    >
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        {hint && <span className="mt-0.5 block text-xs leading-relaxed text-faint">{hint}</span>}
      </span>
      <span
        className={cx(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
          checked ? "bg-ink" : "bg-line",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 h-4 w-4 rounded-full bg-panel shadow-sm transition-all",
            checked ? "left-4.5" : "left-0.5",
          )}
        />
      </span>
    </button>
  );
}

/** Numeric tuning control: slider for the feel, number box for the exact value. */
export function Slider({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step = 1,
  unit,
  isDefault,
}: {
  label: string;
  hint?: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  isDefault?: boolean;
}) {
  return (
    <div className="rounded-lg border border-line bg-panel px-3.5 py-3">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm font-medium text-ink">{label}</span>
        <span className="flex items-center gap-2">
          {!isDefault && <Badge tone="warn">changed</Badge>}
          <input
            type="number"
            value={value}
            min={min}
            max={max}
            step={step}
            onChange={(e) => onChange(Number(e.target.value))}
            className="w-20 rounded-md border border-line bg-raised px-2 py-1 text-right font-mono text-xs text-ink outline-none focus:border-brand"
          />
          {unit && <span className="w-5 text-xs text-faint">{unit}</span>}
        </span>
      </div>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2.5 w-full"
      />
      {hint && <p className="mt-1.5 text-xs leading-relaxed text-faint">{hint}</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- signals */

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "live" | "warn" | "bad" | "brand";
  children: ReactNode;
}) {
  const tones = {
    neutral: "bg-raised text-muted",
    live: "bg-listening/12 text-listening",
    warn: "bg-thinking/12 text-thinking",
    bad: "bg-escalate/12 text-escalate",
    brand: "bg-brand-soft text-brand",
  } as const;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ tone, pulse }: { tone: string; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2">
      {pulse && (
        <span
          className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-70"
          style={{ background: tone }}
        />
      )}
      <span
        className="relative inline-flex h-2 w-2 rounded-full"
        style={{ background: tone }}
      />
    </span>
  );
}

export function Tabs<T extends string>({
  tabs,
  active,
  onSelect,
}: {
  tabs: readonly T[];
  active: T;
  onSelect: (t: T) => void;
}) {
  return (
    <nav className="flex gap-1 border-b border-line">
      {tabs.map((t) => (
        <button
          key={t}
          onClick={() => onSelect(t)}
          className={cx(
            "-mb-px border-b-2 px-3 py-2.5 text-sm transition-colors",
            active === t
              ? "border-ink text-ink"
              : "border-transparent text-muted hover:text-ink",
          )}
        >
          {t}
        </button>
      ))}
    </nav>
  );
}
