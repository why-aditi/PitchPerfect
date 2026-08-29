import CallWidget from "@/components/CallWidget";
import { getPricing } from "@/lib/api";
import type { Pricing } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  // Same pricing.json the agent's get_pricing tool reads, so page and agent
  // can never contradict each other (PRD 10).
  let pricing: Pricing | null = null;
  try {
    pricing = await getPricing();
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
            <code className="font-mono">uvicorn backend.main:app --reload</code>.
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
      <CallWidget />
    </>
  );
}
