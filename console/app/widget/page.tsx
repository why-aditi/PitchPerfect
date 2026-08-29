"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import CallWidget from "@/components/CallWidget";

/**
 * What the embed iframe loads. Chrome-free and transparent, so the host page sees only
 * the launcher and the dialer panel (PRD 6.5).
 */
function Widget() {
  const agentId = useSearchParams().get("agent");

  if (!agentId) {
    return <p className="p-4 text-sm text-red-600">Missing agent parameter.</p>;
  }
  return (
    <div className="flex min-h-screen items-end justify-end bg-transparent p-2">
      <CallWidget agentId={agentId} />
    </div>
  );
}

export default function WidgetPage() {
  return (
    <Suspense>
      <Widget />
    </Suspense>
  );
}
