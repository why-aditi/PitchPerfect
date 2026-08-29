import Link from "next/link";
import type { Metadata } from "next";
import { PricingTable } from "@/components/pricing-table";
import { IconArrow } from "@/components/icons";
import { getPricing } from "@/lib/api";
import type { Pricing } from "@/lib/types";

// Never cached. A price cached on this page while the agent quotes a newly saved one is the
// exact contradiction PRD 10.2 exists to prevent.
export const dynamic = "force-dynamic";

const DEMO_AGENT = process.env.NEXT_PUBLIC_DEMO_AGENT_ID ?? "ag_demo";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Per-seat pricing for Vantage, billed annually, with volume breaks as your seat count grows. Every plan includes the open API.",
};

const FAQ = [
  {
    q: "How does the volume break work?",
    a: "It applies to every seat, not just the ones above the threshold. Cross the break mid-term and the new rate starts on your next invoice — we do not make you re-sign to get it.",
  },
  {
    q: "What happens when we outgrow a plan?",
    a: "You move up at the seat range boundary and keep the same workspace, history and integrations. There is no migration and no re-implementation between plans.",
  },
  {
    q: "Do you charge for API calls?",
    a: "No. REST and webhooks are included on every plan with no per-call fee and no connector licence. Rate limits are published and generous.",
  },
  {
    q: "Can we pay monthly?",
    a: "The rates shown are annual. Monthly billing is available on Growth and Enterprise at a 15% premium; talk to sales if that is the shape you need.",
  },
];

function BackendDown() {
  return (
    <div className="rounded-2xl border border-rule bg-paper p-8 sm:p-10">
      <p className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent-soft px-3 py-1 text-xs font-medium text-accent">
        <span className="size-1.5 rounded-full bg-accent" aria-hidden="true" />
        Pricing service unavailable
      </p>
      <h2 className="font-display mt-5 text-3xl leading-tight tracking-tight">
        This table is generated, not written.
      </h2>
      <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-ink-muted">
        Every row comes from the demo agent&rsquo;s own pricing config, so the page and the
        voice agent can never quote different numbers. With the backend down there is nothing
        honest to show, so it shows nothing. Start the API and seed the demo agent:
      </p>
      <div className="mt-6 space-y-2">
        {["uvicorn backend.main:app --reload", "python -m backend.seed"].map((cmd) => (
          <p
            key={cmd}
            className="overflow-x-auto rounded-lg border border-rule bg-sand/60 px-4 py-3 font-mono text-[13px] whitespace-pre text-ink"
          >
            <span className="mr-2 text-ink-faint select-none">$</span>
            {cmd}
          </p>
        ))}
      </div>
      <p className="mt-5 text-sm text-ink-faint">
        Then reload. The agent id this page asks for is{" "}
        <code className="font-mono text-ink-muted">{DEMO_AGENT}</code>.
      </p>
    </div>
  );
}

export default async function PricingPage() {
  // Same knowledge the agent's get_pricing tool reads, so the page and the agent cannot
  // contradict each other (PRD 10.2). A dead backend is a rendered state, not a 500 — the
  // build has to survive with nothing running.
  let pricing: Pricing | null = null;
  try {
    pricing = await getPricing(DEMO_AGENT);
  } catch {
    pricing = null;
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-5 pt-16 pb-8 sm:px-8 sm:pt-20">
      <header className="max-w-3xl">
        <p className="text-xs font-semibold tracking-[0.18em] text-ink-faint uppercase">Pricing</p>
        <h1 className="font-display mt-4 text-5xl leading-[0.98] tracking-tight text-balance sm:text-6xl">
          Per seat. Cheaper as the org grows.
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-ink-muted">
          One workspace, every team in it. Prices are per seat per month, billed annually, and
          include the open API on every plan.
        </p>
      </header>

      <div className="mt-12">{pricing ? <PricingTable pricing={pricing} /> : <BackendDown />}</div>

      <section aria-labelledby="faq-heading" className="mt-20 border-t border-rule pt-14">
        <h2
          id="faq-heading"
          className="font-display text-4xl leading-tight tracking-tight text-balance"
        >
          The questions procurement always asks.
        </h2>
        <dl className="mt-10 grid gap-x-12 gap-y-9 md:grid-cols-2">
          {FAQ.map((item) => (
            <div key={item.q}>
              <dt className="text-base font-semibold tracking-tight">{item.q}</dt>
              <dd className="mt-2 text-[15px] leading-relaxed text-ink-muted">{item.a}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-16 flex flex-col items-start gap-6 rounded-3xl bg-brand-deep p-8 text-paper sm:p-12 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-3xl leading-tight tracking-tight text-balance sm:text-4xl">
            Not sure which plan your seat count lands in?
          </h2>
          <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-brand-soft/80">
            The Talk to Sales button in the corner of this page opens a live call — bring your
            seat count and your renewal date and you will leave with a number. Or read how two
            customers sized their migration first.
          </p>
        </div>
        <Link
          href="/customers"
          className="inline-flex shrink-0 items-center gap-2 rounded-full bg-paper px-6 py-3.5 text-sm font-medium text-brand-deep transition-colors hover:bg-brand-soft"
        >
          Read the migrations
          <IconArrow className="size-4" />
        </Link>
      </section>
    </div>
  );
}
