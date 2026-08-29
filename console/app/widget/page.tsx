"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";
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
  return (
    <>
      {/* The console's chrome and opaque background belong to the console, not to an
          iframe sitting on someone else's pricing page. `color-scheme` is reset with them:
          a dark scheme makes the UA paint the canvas, which is the one thing that keeps an
          otherwise transparent iframe from disappearing into the host page. */}
      <style href="pitchpilot-widget-chrome" precedence="high">
        {`html { color-scheme: normal; background: transparent; }
          body { background: transparent; }
          body > header { display: none; }`}
      </style>
      <Suspense>
        <Widget />
      </Suspense>
    </>
  );
}
