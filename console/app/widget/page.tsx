"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";
import CallWidget from "@/components/CallWidget";

/**
 * Appearance arrives in the URL from the embed snippet, so it is whatever a stranger typed
 * on their own page. Both are looked up in a map rather than interpolated into a class
 * name: an unknown value falls back to the default instead of emitting a class that
 * matches nothing and renders an unstyled widget on a customer's site.
 *
 * theme-light is the same palette as theme-ink and stays the fallback, so an embed written
 * before any of this existed renders exactly as it did.
 */
const THEMES: Record<string, string> = {
  ink: "theme-ink",
  forest: "theme-forest",
  crimson: "theme-crimson",
  frost: "theme-frost",
  cobalt: "theme-cobalt",
  amber: "theme-amber",
};

const SHAPES: Record<string, string> = {
  pill: "shape-pill",
  rounded: "shape-rounded",
  square: "shape-square",
};

function appearance(params: URLSearchParams): string {
  const theme = THEMES[params.get("theme") ?? ""] ?? "theme-light";
  const shape = SHAPES[params.get("shape") ?? ""] ?? "shape-pill";
  return `${theme} ${shape}`;
}

/**
 * What the embed iframe loads. Chrome-free and transparent, so the host page sees only the
 * launcher and the dialer panel (PRD 6.5).
 *
 * The loader mounts the iframe collapsed to launcher size and grows it only on our
 * message, so the host page's bottom-right corner stays clickable while the widget is
 * idle. Measuring is the only honest way to size it: the transcript makes the panel's
 * height dynamic, and a hardcoded pair of sizes would clip it.
 */
function Widget() {
  const params = useSearchParams();
  const agentId = params.get("agent");
  // Set by the embed loader from the host page; absent when opened directly.
  const pageOrigin = params.get("origin") ?? undefined;
  const root = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = root.current;
    // Opened directly at /widget?agent=… for development there is no parent to tell.
    if (!el || window.parent === window) return;

    const post = () => {
      const box = el.getBoundingClientRect();
      window.parent.postMessage(
        {
          source: "pitchpilot",
          type: "resize",
          width: Math.ceil(box.width),
          height: Math.ceil(box.height),
        },
        "*",
      );
    };

    const observer = new ResizeObserver(post);
    observer.observe(el);
    post();
    return () => observer.disconnect();
  }, [agentId]);

  const skin = appearance(params);

  if (!agentId) {
    // Themed too, and not for tidiness: this branch used to return before the wrapper, so
    // on a dark-OS visitor it resolved its colours from the dark block and rendered the
    // one thing on screen in the wrong palette.
    return (
      <p
        className={`${skin} m-3 rounded-lg border border-escalate/40 bg-escalate/10 px-3 py-2 text-xs text-escalate`}
      >
        This widget was loaded without an <code className="font-mono">agent</code> parameter,
        so there is nothing to call.
      </p>
    );
  }

  return (
    // The theme class pins the palette, and pinning it is not a preference: an iframe reads
    // prefers-color-scheme from the visitor's OS, not from the page it is sitting on, so a
    // visitor in dark mode was getting the dark palette painted onto a light host site.
    // Which palette is a choice — themes are named in globals.css — but following the
    // visitor's OS is never one of the options, because it tracks the wrong thing.
    //
    // A class rather than the data-theme attribute globals.css also honours, because the
    // attribute belongs on <html> and only the root layout renders that. Reaching it meant
    // an inline script, which brought three problems with it — a nonce needed under any
    // strict CSP, a React dev warning for rendering a <script>, and Strict Mode's dev
    // remount wiping attributes React does not manage from JSX, in the one mode this is
    // run in. Custom properties resolve from the nearest ancestor that sets them, so a
    // class here beats the dark block on :root by proximity and none of that applies.
    // Bottom-right on a host page, because that is the corner the loader sizes the iframe
    // into. Centred only for the console's own preview box, where there is no corner to
    // belong to and an off-centre launcher just looks like a layout bug.
    <div
      className={`${skin} fixed inset-0 flex ${
        params.get("preview") ? "items-center justify-center" : "items-end justify-end"
      }`}
    >
      {/* The padding is inside the measured box, so the panel's shadow is not clipped by
          the iframe edge. */}
      <div ref={root} className="inline-block p-3">
        <CallWidget agentId={agentId} pageOrigin={pageOrigin} />
      </div>
    </div>
  );
}

export default function WidgetPage() {
  return (
    <>
      {/* The console's chrome and opaque background belong to the console, not to an
          iframe sitting on someone else's pricing page. `color-scheme` is reset with them:
          a dark scheme makes the UA paint the canvas, which is the one thing that keeps an
          otherwise transparent iframe from disappearing into the host page.

          !important on all three, and it is load-bearing rather than lazy. globals.css
          paints html and body with var(--surface) from its base layer, and sets
          color-scheme on :root:not([data-theme="light"]). Plain `html { background:
          transparent }` ties that base rule on specificity and loses on source order, and
          the color-scheme reset loses outright to the more specific selector — so this
          override silently did nothing and the widget rendered as a black rectangle on
          the host page. Beating both without depending on injection order is the point. */}
      <style href="pitchpilot-widget-chrome" precedence="high">
        {`html, body { background: transparent !important; }
          :root { color-scheme: normal !important; }
          body > header { display: none; }`}
      </style>
      <Suspense>
        <Widget />
      </Suspense>
    </>
  );
}
