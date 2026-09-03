"use client";

import { useState } from "react";
import { Button, Card, cx, Field, Input } from "@/components/ui";
import { CopyButton, Group, Hint, IconButton, IconPlus, IconTrash, Warn } from "./bits";

/**
 * Named, not a colour picker. The ratios for each of these are checked against the widget's
 * own panel in advance, and a free hue would also let someone collapse the listening green
 * into the speaking blue — the pair whose overlap is how barge-in reads on screen.
 */
type ThemeName = "ink" | "forest" | "crimson" | "frost" | "cobalt" | "amber";
type ShapeName = "pill" | "rounded" | "square";

type ThemeOption = {
  name: ThemeName;
  label: string;
  hint: string;
  /** Launcher and panel, in that order — the two surfaces a theme actually paints. */
  swatch: [string, string];
  /** Only used to open the preview on the backdrop the theme was built for. */
  dark: boolean;
};

/**
 * One list, not a light group and a dark group. The swatch already says which is which —
 * it is a picture of the thing — and splitting six options into two rows of three made a
 * choice out of something nobody was choosing, while pushing the last row below the fold.
 *
 * One hue each: black, green, red, white, blue, gold. Two earlier passes got this wrong
 * the same way twice — first every launcher was a flavour of near-black, then two were
 * green and two were blue with one light and one dark of each, which is four hues wearing
 * six names. None of these is a lightness variant of another.
 */
const THEMES: ThemeOption[] = [
  {
    name: "ink",
    label: "Ink",
    hint: "Neutral black. Sits on any host without competing with it — the default.",
    swatch: ["#15181d", "#ffffff"],
    dark: false,
  },
  {
    name: "forest",
    label: "Forest",
    hint: "Deep green. The one that belongs on the Vantage demo site.",
    swatch: ["#0e5049", "#ffffff"],
    dark: false,
  },
  {
    name: "crimson",
    label: "Crimson",
    hint: "Deep red — not a bright one, so it does not borrow the urgency of the escalation colour.",
    swatch: ["#a32638", "#ffffff"],
    dark: false,
  },
  {
    name: "frost",
    label: "Frost",
    hint: "A pale launcher on a dark panel. Inverted from the rest, and what stands out on a dark page.",
    swatch: ["#e8ecf1", "#141a1f"],
    dark: true,
  },
  {
    name: "cobalt",
    label: "Cobalt",
    hint: "Blue on navy. The most common brand colour there is.",
    swatch: ["#1d4ed8", "#0f172a"],
    dark: true,
  },
  {
    name: "amber",
    label: "Amber",
    hint: "Gold on a warm dark panel. Takes dark text, like Frost.",
    swatch: ["#b7791f", "#1a1408"],
    dark: true,
  },
];

const SHAPES: { name: ShapeName; label: string; radius: string }[] = [
  { name: "pill", label: "Pill", radius: "9999px" },
  { name: "rounded", label: "Rounded", radius: "0.75rem" },
  { name: "square", label: "Square", radius: "0.1875rem" },
];

/**
 * The origin list is compared against the browser's Origin header on /start-call, so it has
 * to be exactly what a browser sends: scheme, host, optional port, nothing else. A trailing
 * path here is a call that gets refused with no explanation on the host page.
 */
export function originError(raw: string): string | null {
  const value = raw.trim();
  if (!value) return "Empty.";

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return "Include the scheme, like https://example.com";
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return "Only http and https.";
  if (url.username || url.password) return "No credentials in an origin.";
  if (url.search || url.hash || (url.pathname !== "/" && url.pathname !== ""))
    return `An origin is scheme and host only — use ${url.origin}`;
  if (value !== url.origin && value !== `${url.origin}/`) return `Use ${url.origin}`;
  return null;
}

/**
 * The real widget route in an iframe, not a mock of it.
 *
 * A hand-built swatch would be a second copy of the launcher's markup, and the first time
 * someone changed a radius or a shadow in CallWidget the preview would start lying — which
 * is worse than no preview, because the operator would trust it. This renders exactly what
 * a host page renders, through exactly the same CSS.
 *
 * pointer-events are off: the launcher inside is live, and a click would start a real call
 * and spend real engine minutes from a settings screen.
 *
 * The backdrop toggle is the actual question being asked here. Every ratio inside the
 * widget is against its own panel and holds anywhere; the one unknowable is how the
 * launcher sits on the host's own background, so the preview lets you put it on both.
 */
function Preview({ id, theme, shape }: { id: string; theme: ThemeName; shape: ShapeName }) {
  // Opens on the backdrop the theme was designed for — the component is keyed on theme, so
  // switching to a dark theme shows it on dark first rather than leaving it on a light
  // panel looking broken. Toggling from there is the point, and survives a shape change.
  const [dark, setDark] = useState(() => THEMES.find((t) => t.name === theme)?.dark ?? false);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-ink">Preview</p>
        <div className="flex gap-1">
          {[
            { label: "On light", value: false },
            { label: "On dark", value: true },
          ].map((option) => (
            <button
              key={option.label}
              type="button"
              aria-pressed={dark === option.value}
              onClick={() => setDark(option.value)}
              className={cx(
                "rounded-md px-2 py-1 text-xs transition-colors",
                dark === option.value ? "bg-raised text-ink" : "text-faint hover:text-muted",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div
        className="overflow-hidden rounded-xl border border-line"
        style={{ background: dark ? "#101418" : "#faf7f1" }}
      >
        <iframe
          // Keyed so switching theme or shape remounts rather than relying on the route to
          // react to a changed query string.
          key={`${theme}-${shape}`}
          title="Widget preview"
          src={`/widget?agent=${encodeURIComponent(id)}&theme=${theme}&shape=${shape}&preview=1`}
          className="pointer-events-none block h-[104px] w-full border-0 bg-transparent"
        />
      </div>
    </div>
  );
}

export function EmbedTab({
  id,
  isNew,
  origins,
  onChange,
}: {
  id: string;
  isNew: boolean;
  origins: string[];
  onChange: (next: string[]) => void;
}) {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  // Appearance lives on the snippet rather than in the agent, because the design it has to
  // sit inside belongs to the host page. This picker only writes the string to copy —
  // nothing is saved, and pasting the snippet on a second site with different attributes
  // is a supported thing to do rather than a conflict.
  const [theme, setTheme] = useState<ThemeName>("ink");
  const [shape, setShape] = useState<ShapeName>("pill");
  const attrs = [
    `src="${apiBase}/embed.js?agent=${id}"`,
    theme !== "ink" ? `data-theme="${theme}"` : null,
    shape !== "pill" ? `data-shape="${shape}"` : null,
    "async",
  ].filter(Boolean);
  const snippet = `<script ${attrs.join(" ")}></script>`;

  const trimmed = origins.map((o) => o.trim()).filter(Boolean);
  const duplicated = trimmed.filter((o, i) => trimmed.indexOf(o) !== i);

  return (
    <div className="space-y-10">
      <Group title="Embed snippet">
        {isNew ? (
          <p className="rounded-xl border border-dashed border-line px-6 py-8 text-center text-sm text-muted">
            The snippet carries the agent id, so it appears once you have created the agent.
          </p>
        ) : (
          <Card className="space-y-3 p-4">
            <pre className="overflow-x-auto rounded-lg border border-line-soft bg-surface p-3 font-mono text-xs leading-relaxed text-ink">
              {snippet}
            </pre>
            <div className="flex items-center justify-between gap-4">
              <Hint>
                Paste it anywhere in the page. It injects a launcher and an iframe carrying
                allow=&quot;microphone&quot;, so the host page has to be on HTTPS for the mic
                prompt to appear.
              </Hint>
              <CopyButton text={snippet} label="Copy snippet" />
            </div>

            <div className="grid gap-5 border-t border-line-soft pt-4 sm:grid-cols-2">
              <Field
                label="Theme"
                hint="The widget cannot see the page it lands on, so this is the only thing that tells it."
              >
                <div className="flex flex-wrap gap-2">
                  {THEMES.map((t) => (
                    <button
                      key={t.name}
                      type="button"
                      title={t.hint}
                      aria-pressed={theme === t.name}
                      onClick={() => setTheme(t.name)}
                      className={cx(
                        "flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors",
                        theme === t.name
                          ? "border-brand bg-brand-soft text-ink"
                          : "border-line text-muted hover:border-brand/50",
                      )}
                    >
                      <span
                        aria-hidden
                        className="h-4 w-4 rounded-full border border-line"
                        style={{
                          background: `linear-gradient(135deg, ${t.swatch[0]} 50%, ${t.swatch[1]} 50%)`,
                        }}
                      />
                      {t.label}
                    </button>
                  ))}
                </div>
              </Field>

              <Field label="Shape" hint="Applies to the launcher and the call panel together.">
                <div className="flex flex-wrap gap-2">
                  {SHAPES.map((s) => (
                    <button
                      key={s.name}
                      type="button"
                      aria-pressed={shape === s.name}
                      onClick={() => setShape(s.name)}
                      className={cx(
                        "flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors",
                        shape === s.name
                          ? "border-brand bg-brand-soft text-ink"
                          : "border-line text-muted hover:border-brand/50",
                      )}
                    >
                      <span
                        aria-hidden
                        className="h-4 w-6 border border-current opacity-60"
                        style={{ borderRadius: s.radius }}
                      />
                      {s.label}
                    </button>
                  ))}
                </div>
              </Field>
            </div>

            <Preview key={theme} id={id} theme={theme} shape={shape} />

            <Hint>
              Both are attributes on the tag, so the same agent can look different on two
              sites. Nothing here is saved with the agent — copy the snippet again after
              changing them.
            </Hint>
          </Card>
        )}
      </Group>

      <Group
        title="Allowed origins"
        action={
          <Button
            variant="ghost"
            className="px-3 py-1.5 text-xs"
            onClick={() => onChange([...origins, ""])}
          >
            <IconPlus />
            Add origin
          </Button>
        }
      >
        <Hint>
          A call from an origin that is not on this list is refused before it starts. The list is
          the control that matters on this surface, so an empty list means the embed works
          nowhere — including on your own demo page.
        </Hint>

        {origins.length === 0 && (
          <Warn>
            No origins listed. Every call from the embed will be refused until one is added.
          </Warn>
        )}
        {duplicated.length > 0 && <Warn>{duplicated[0]} is listed twice.</Warn>}

        <div className="space-y-2">
          {origins.map((origin, i) => {
            const error = origin.trim() ? originError(origin) : null;
            return (
              // Index keys: rows are plain strings the operator reorders by editing, not by
              // dragging, so there is no identity to key on.
              <div key={i} className="space-y-1">
                <div className="flex items-center gap-2">
                  <Input
                    value={origin}
                    spellCheck={false}
                    placeholder="https://vantage.example.com"
                    onChange={(e) =>
                      onChange(origins.map((o, n) => (n === i ? e.target.value : o)))
                    }
                    className="font-mono"
                  />
                  <IconButton
                    label="Remove origin"
                    tone="danger"
                    onClick={() => onChange(origins.filter((_, n) => n !== i))}
                  >
                    <IconTrash />
                  </IconButton>
                </div>
                {error && <p className="pl-1 text-xs text-escalate">{error}</p>}
              </div>
            );
          })}
        </div>

        <Hint>
          Localhost counts as its own origin: add http://localhost:3000 while you are developing
          the host page.
        </Hint>
      </Group>
    </div>
  );
}
