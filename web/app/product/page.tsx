import Link from "next/link";
import type { Metadata } from "next";
import { ProductShot } from "@/components/product-shot";
import { IconArrow, IconCheck, IconFlow, IconKey, IconRollup } from "@/components/icons";

export const metadata: Metadata = {
  title: "Product",
  description:
    "How Vantage works: automation that lives next to the work, rollups that are current by construction, and an open API with no per-call fees.",
};

const SECTIONS = [
  {
    id: "automations",
    icon: IconFlow,
    eyebrow: "Automations",
    title: "The rule lives on the board it acts on.",
    body: "Most teams end up with a second product just to move work between the first ones — its own login, its own bill, its own outage. In Vantage a rule is a property of the board: pick a trigger, pick what happens, and the people who own the work can read it without asking an admin what it does.",
    points: [
      "Triggers on status, date, field change, form submission or an inbound webhook.",
      "Actions create work, reassign it, set dates, post to a channel or call your endpoint.",
      "Every run is logged with its trigger and result, so a misfire is a five-second diagnosis.",
      "Non-technical owners write them. There is no expression language to learn.",
    ],
  },
  {
    id: "rollups",
    icon: IconRollup,
    eyebrow: "Rollups",
    title: "Reporting stops being a project.",
    body: "A rollup is not a scheduled export. Values propagate from the task to the workstream to the portfolio the moment they change, which means the number in the board pack is the number on the board — and nobody spends the last day of the quarter reconciling four exports into one slide.",
    points: [
      "Roll up any numeric or date field across any grouping you already use.",
      "Portfolio views compare workstreams across teams without a shared naming convention.",
      "Snapshots keep history, so you can show the trend and not just today.",
      "Share a read-only view with finance or a customer without buying them a seat.",
    ],
  },
  {
    id: "api",
    icon: IconKey,
    eyebrow: "Platform",
    title: "An open API, and no meter on it.",
    body: "Integration pricing is where work-management tools quietly become expensive. Vantage does not charge per API call and does not sell connectors: the REST API and webhooks are on every plan, at the same published rate limits, from the first seat.",
    points: [
      "REST for every object in the workspace, plus signed outbound webhooks.",
      "SSO and audit logs from Growth — not held back behind an Enterprise line item.",
      "SAML, SCIM, a 99.9% uptime SLA and a custom DPA when procurement gets involved.",
      "Import from CSV or from your previous tool, with a dry run before anything is written.",
    ],
  },
];

const NOT_FOR_YOU = [
  "If deep marketing attribution modelling is the job, a dedicated analytics tool will model it better than we do. Plenty of customers keep one and roll its output into Vantage.",
  "If your work is almost entirely in a repository, an engineering-native tracker will have the tighter Git integration. We cover the whole go-to-market org, which is a different centre of gravity.",
];

export default function ProductPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-5 pt-16 pb-8 sm:px-8 sm:pt-20">
      <header className="max-w-3xl">
        <p className="text-xs font-semibold tracking-[0.18em] text-ink-faint uppercase">Product</p>
        <h1 className="font-display mt-4 text-5xl leading-[0.98] tracking-tight text-balance sm:text-6xl">
          One place where the plan and the work are the same object.
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-ink-muted">
          Vantage holds the plan, the delivery and the numbers together. Below is what that
          actually means day to day — and, at the bottom, where it is honestly not the right
          tool.
        </p>
      </header>

      <div className="mt-14">
        <ProductShot />
      </div>

      <div className="mt-20 space-y-20">
        {SECTIONS.map(({ id, icon: Icon, eyebrow, title, body, points }) => (
          <section key={id} id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-24">
            <div className="grid gap-8 border-t border-rule pt-10 lg:grid-cols-[1fr_1.15fr] lg:gap-16">
              <div>
                <p className="flex items-center gap-2.5 text-xs font-semibold tracking-[0.18em] text-ink-faint uppercase">
                  <Icon className="size-5 text-brand" />
                  {eyebrow}
                </p>
                <h2
                  id={`${id}-heading`}
                  className="font-display mt-5 text-4xl leading-[1.05] tracking-tight text-balance"
                >
                  {title}
                </h2>
              </div>
              <div>
                <p className="text-[15px] leading-relaxed text-ink-muted">{body}</p>
                <ul className="mt-6 space-y-3">
                  {points.map((point) => (
                    <li key={point} className="flex gap-3 text-[15px] leading-relaxed">
                      <IconCheck className="mt-1 size-4 shrink-0 text-accent" />
                      <span className="text-ink-muted">{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        ))}
      </div>

      <section
        aria-labelledby="honest-heading"
        className="mt-20 rounded-3xl border border-rule bg-sand/60 p-8 sm:p-12"
      >
        <h2
          id="honest-heading"
          className="font-display text-4xl leading-tight tracking-tight text-balance"
        >
          Where Vantage is not the answer.
        </h2>
        <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-muted">
          Two things we lose on, said here rather than discovered in month four.
        </p>
        <ul className="mt-8 grid gap-6 md:grid-cols-2">
          {NOT_FOR_YOU.map((item) => (
            <li
              key={item}
              className="rounded-2xl border border-rule bg-paper p-6 text-[15px] leading-relaxed text-ink-muted"
            >
              {item}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-16 flex flex-col items-start gap-6 md:flex-row md:items-center md:justify-between">
        <h2 className="font-display text-3xl leading-tight tracking-tight text-balance">
          See what a seat costs at your size.
        </h2>
        <Link
          href="/pricing"
          className="inline-flex shrink-0 items-center gap-2 rounded-full bg-brand px-6 py-3.5 text-sm font-medium text-paper transition-colors hover:bg-brand-deep"
        >
          See pricing
          <IconArrow className="size-4" />
        </Link>
      </section>
    </div>
  );
}
