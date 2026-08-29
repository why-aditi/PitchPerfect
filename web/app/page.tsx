import Script from "next/script";
import { getPricing } from "@/lib/api";
import type { Pricing } from "@/lib/types";

export const dynamic = "force-dynamic";

const DEMO_AGENT = process.env.NEXT_PUBLIC_DEMO_AGENT_ID ?? "ag_demo";
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default async function Home() {
  // Same knowledge the agent's get_pricing tool reads, so the page and the agent
  // cannot contradict each other (PRD 10.2).
  let pricing: Pricing | null = null;
  try {
    pricing = await getPricing(DEMO_AGENT);
  } catch {
    pricing = null;
  }

  return (
    <>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-16">
        <h1 className="text-4xl font-semibold tracking-tight">Pricing</h1>
        <p className="mt-2 text-neutral-500">Per seat, per month. Billed annually.</p>

        {!pricing ? (
          <p className="mt-10 rounded-lg border border-dashed p-6 text-sm text-neutral-500">
            Backend not reachable. Start it with{" "}
            <code className="font-mono">uvicorn backend.main:app --reload</code> and seed the
            demo agent with <code className="font-mono">python -m backend.seed</code>.
          </p>
        ) : (
          <section className="mt-10 grid gap-4 sm:grid-cols-3">
            {pricing.tiers.map((t) => (
              <article
                key={t.name}
                className="rounded-xl border border-neutral-200 p-6 dark:border-neutral-700"
              >
                <h2 className="text-lg font-medium">{t.name}</h2>
                <p className="mt-1 text-3xl font-semibold">
                  ${t.per_seat_month}
                  <span className="text-sm font-normal text-neutral-500">/seat/mo</span>
                </p>
                <p className="mt-1 text-sm text-neutral-500">
                  {t.max_seats ? `${t.min_seats}–${t.max_seats} seats` : `${t.min_seats}+ seats`}
                </p>
                {t.volume_break && (
                  <p className="text-sm text-neutral-500">
                    ${t.volume_break.per_seat_month}/seat from {t.volume_break.seats}
                  </p>
                )}
                <ul className="mt-4 space-y-1 text-sm">
                  {t.features.map((f) => (
                    <li key={f}>· {f}</li>
                  ))}
                </ul>
              </article>
            ))}
          </section>
        )}
      </main>

      {/*
        The entire voice integration. This page bundles no widget code, no Agora SDK and
        nothing from the console — if the embed breaks, this page shows it (PRD 10.2).
      */}
      <Script src={`${API}/embed.js?agent=${DEMO_AGENT}`} strategy="afterInteractive" />
    </>
  );
}
