import Link from "next/link";
import type { Metadata } from "next";
import { ProductShot } from "@/components/product-shot";
import { CUSTOMER_MARKS } from "@/components/logos";
import {
  IconArrow,
  IconClock,
  IconFlow,
  IconKey,
  IconLayers,
  IconQuote,
  IconRollup,
  IconShield,
} from "@/components/icons";

export const metadata: Metadata = {
  title: "Vantage — the system of action for go-to-market teams",
  description:
    "Plan, hand off and ship in one place. Native automation, live rollups and an open API, running in days rather than a six-week onboarding.",
};

const FEATURES = [
  {
    icon: IconFlow,
    title: "Automation that lives next to the work",
    body: "Rules sit on the board they act on, not in a separate automation product with its own login and its own invoice. When a deal moves to contracting, the implementation plan, its owner and the kickoff date are already there.",
  },
  {
    icon: IconRollup,
    title: "Rollups, not a reporting project",
    body: "Every field rolls up the moment it changes, from the task to the workstream to the board pack. Nobody spends Friday reconciling four tools into a slide that is stale before the meeting starts.",
  },
  {
    icon: IconClock,
    title: "Live in days, not a six-week onboarding",
    body: "Import a spreadsheet, pick a template, invite the team. Most customers are running real work in the first week and have retired their old workspace inside a month.",
  },
  {
    icon: IconKey,
    title: "An open API with no per-call fees",
    body: "REST endpoints and webhooks on every plan, metered by nothing. Build the integration your operations team actually needs instead of paying for a connector that does eighty percent of it.",
  },
];

const INCLUDED = [
  { icon: IconShield, text: "SSO and audit logs on Growth — not held back for Enterprise." },
  { icon: IconLayers, text: "SAML, SCIM and a custom DPA when procurement asks." },
  { icon: IconClock, text: "A 99.9% uptime SLA and a named CSM on Enterprise." },
];

const STATS = [
  { value: "340", label: "seats migrated in one quarter" },
  { value: "9h → 40m", label: "weekly reporting time at Kestrel" },
  { value: "3 → 1", label: "workspaces consolidated at Halden Group" },
  { value: "2 wks", label: "from pilot to production" },
];

export default function Home() {
  return (
    <>
      <section className="mx-auto w-full max-w-6xl px-5 pt-16 pb-6 sm:px-8 sm:pt-24">
        <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-rule bg-paper px-3 py-1 text-xs font-medium tracking-wide text-ink-muted">
              <span className="size-1.5 rounded-full bg-accent" aria-hidden="true" />
              Work management for the whole go-to-market org
            </p>

            <h1 className="font-display mt-6 text-5xl leading-[0.95] tracking-tight text-balance sm:text-6xl lg:text-7xl">
              Stop reporting on the work. Start running it.
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-muted">
              Vantage is where go-to-market, operations and delivery teams plan, hand off and
              ship. The plan, the work and the numbers sit in one system — so the status update
              is a side effect of doing the job, not a second job.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/pricing"
                className="inline-flex items-center gap-2 rounded-full bg-brand px-5 py-3 text-sm font-medium text-paper transition-colors hover:bg-brand-deep"
              >
                See plans and pricing
                <IconArrow className="size-4" />
              </Link>
              <Link
                href="/product"
                className="inline-flex items-center gap-2 rounded-full border border-rule-strong bg-paper px-5 py-3 text-sm font-medium transition-colors hover:border-ink/30"
              >
                Take the product tour
              </Link>
            </div>

            <p className="mt-5 max-w-md text-sm text-ink-faint">
              Sizing a migration or a seat count? The{" "}
              <strong className="font-medium text-ink-muted">Talk to Sales</strong> button in the
              corner of this page starts a live call.
            </p>
          </div>

          <div className="lg:pl-4">
            <ProductShot />
          </div>
        </div>
      </section>

      <section
        aria-labelledby="customers-heading"
        className="mx-auto w-full max-w-6xl px-5 py-16 sm:px-8"
      >
        <h2
          id="customers-heading"
          className="text-center text-xs font-semibold tracking-[0.18em] text-ink-faint uppercase"
        >
          Planning and shipping on Vantage today
        </h2>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-12 gap-y-8 text-ink/45">
          {CUSTOMER_MARKS.map((Mark, i) => (
            <Mark key={i} className="h-6 shrink-0" />
          ))}
        </div>
      </section>

      <section
        aria-labelledby="features-heading"
        className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8"
      >
        <h2
          id="features-heading"
          className="font-display max-w-2xl text-4xl leading-tight tracking-tight text-balance sm:text-5xl"
        >
          One system of action, from the pipeline review to the shipped thing.
        </h2>

        <div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-rule bg-rule sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <article key={title} className="bg-paper p-7 sm:p-9">
              <Icon className="size-6 text-brand" />
              <h3 className="mt-5 text-lg font-semibold tracking-tight">{title}</h3>
              <p className="mt-2.5 text-[15px] leading-relaxed text-ink-muted">{body}</p>
            </article>
          ))}
        </div>

        <ul className="mt-8 grid gap-4 sm:grid-cols-3">
          {INCLUDED.map(({ icon: Icon, text }) => (
            <li
              key={text}
              className="flex gap-3 rounded-xl border border-rule bg-sand/50 px-4 py-3.5 text-sm text-ink-muted"
            >
              <Icon className="size-5 shrink-0 text-accent" />
              {text}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="proof-heading" className="mx-auto w-full max-w-6xl px-5 py-16 sm:px-8">
        <div className="overflow-hidden rounded-3xl bg-brand-deep text-paper">
          <div className="grid gap-10 p-8 sm:p-12 lg:grid-cols-[1.3fr_1fr] lg:gap-16">
            <figure>
              <IconQuote className="h-6 text-accent" />
              <h2 id="proof-heading" className="sr-only">
                What customers say
              </h2>
              <blockquote className="font-display mt-6 text-3xl leading-[1.15] tracking-tight text-balance sm:text-4xl">
                &ldquo;We moved 340 seats across in a single quarter. Weekly reporting went from
                nine hours to forty minutes, and not one person has asked for the old tool
                back.&rdquo;
              </blockquote>
              <figcaption className="mt-6 text-sm text-brand-soft/80">
                Dana Okonkwo · VP Operations, Kestrel Logistics
              </figcaption>
            </figure>

            <dl className="grid grid-cols-2 gap-8 self-center lg:border-l lg:border-brand-soft/15 lg:pl-12">
              {STATS.map((stat) => (
                <div key={stat.label}>
                  <dt className="sr-only">{stat.label}</dt>
                  <dd>
                    <span className="font-display block text-4xl leading-none tracking-tight">
                      {stat.value}
                    </span>
                    <span className="mt-2 block text-xs leading-relaxed text-brand-soft/70">
                      {stat.label}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>

      <section aria-labelledby="cta-heading" className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8">
        <div className="flex flex-col items-start gap-6 rounded-3xl border border-rule bg-paper p-8 sm:p-12 md:flex-row md:items-center md:justify-between">
          <div>
            <h2
              id="cta-heading"
              className="font-display text-4xl leading-tight tracking-tight text-balance"
            >
              Put the whole org on one plan.
            </h2>
            <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-ink-muted">
              Per-seat pricing with a volume break as you grow, and a migration that finishes in
              weeks. Start with the plans, or talk to someone about your seat count.
            </p>
          </div>
          <Link
            href="/pricing"
            className="inline-flex shrink-0 items-center gap-2 rounded-full bg-brand px-6 py-3.5 text-sm font-medium text-paper transition-colors hover:bg-brand-deep"
          >
            See pricing
            <IconArrow className="size-4" />
          </Link>
        </div>
      </section>
    </>
  );
}
