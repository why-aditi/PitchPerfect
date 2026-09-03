"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useLayoutEffect, useRef } from "react";
import CallWidget from "@/components/CallWidget";

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

  if (!agentId) {
    return (
      <p className="m-3 rounded-lg border border-escalate/40 bg-escalate/10 px-3 py-2 text-xs text-escalate">
        This widget was loaded without an <code className="font-mono">agent</code> parameter,
        so there is nothing to call.
      </p>
    );
  }

  return (
    <div className="fixed inset-0 flex items-end justify-end">
      {/* The padding is inside the measured box, so the panel's shadow is not clipped by
          the iframe edge. */}
      <div ref={root} className="inline-block p-3">
        <CallWidget agentId={agentId} pageOrigin={pageOrigin} />
      </div>
    </div>
  );
}

export default function WidgetPage() {
  // Belt and braces, and the braces are the half that matters here. React's Strict Mode
  // remounts once in development and resets <html> to only the attributes it manages from
  // JSX — which clears the data-theme the inline script set, so the widget silently falls
  // back to the visitor's OS palette. Production never remounts and never needs this, but
  // the console is run with `npm run dev` (the replay fallback on the live page only
  // exists outside a production build), so development is the environment this has to be
  // right in. useLayoutEffect rather than useEffect because it runs before paint.
  useLayoutEffect(() => {
    document.documentElement.setAttribute("data-theme", "light");
  }, []);

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
      {/* The widget is pinned to the light palette, and it is not a preference: the iframe
          reads prefers-color-scheme from the visitor's OS, not from the page it is sitting
          on, so a visitor in dark mode was getting the dark palette painted onto a light
          host site. The host's own design decides what looks right here and we cannot see
          it, so the neutral light one is the only palette that is never actively wrong.
          globals.css already guards every dark rule with :not([data-theme="light"]) — this
          is that escape hatch, set from a parse-time script rather than an effect so the
          launcher is never painted dark for a frame first.

          The type switch is the framework's documented shape for an inline script
          (next/dist/docs .../preventing-flash-before-hydration): text/javascript on the
          server so the browser runs it while parsing, text/plain once hydrated so it
          cannot run twice, and suppressHydrationWarning because those two disagree by
          design. Without it React warns about the script tag in development. */}
      <script
        type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
        suppressHydrationWarning
        dangerouslySetInnerHTML={{
          __html: `document.documentElement.setAttribute("data-theme","light")`,
        }}
      />
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
