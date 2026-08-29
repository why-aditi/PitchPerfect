import Link from "next/link";
import type { Metadata } from "next";
import { HaldenGroup, KestrelLogistics } from "@/components/logos";
import { IconArrow, IconQuote } from "@/components/icons";

export const metadata: Metadata = {
  title: "Customers",
  description:
    "How Kestrel Logistics moved 340 seats and cut weekly reporting from nine hours to forty minutes, and how Halden Group consolidated three workspaces in a two-week pilot.",
};

const STORIES = [
  {
    id: "kestrel",
    mark: KestrelLogistics,
    company: "Kestrel Logistics",
    industry: "Freight and warehousing · 1,400 staff",
    headline: "340 seats moved in a quarter, and Friday got its afternoon back.",
    // The numbers here are the same ones the demo agent quotes from its Northbeam battlecard.
    // If a prospect hears one figure on the call and reads another here, both stop being
    // believable — so the page repeats the proof point rather than inventing a nicer one.
    body: [
      "Kestrel ran planning in one tool and reported out of another. Every Friday, four operations leads pulled exports, reconciled them by hand and rebuilt the same deck — about nine hours a week between them, and the deck was already stale by Monday's review.",
      "They moved 340 seats onto Vantage over a single quarter, one region at a time, keeping the old workspace read-only until the last region cut over. Rollups replaced the export step entirely: the regional numbers now aggregate into the portfolio view as work moves.",
      "The Friday cycle is now about forty minutes, and most of that is commentary rather than assembly. The reporting tool they kept is the one that does attribution modelling, which was never the thing we were replacing.",
    ],
    quote:
      "We moved 340 seats across in a single quarter. Weekly reporting went from nine hours to forty minutes, and not one person has asked for the old tool back.",
    attribution: "Dana Okonkwo · VP Operations, Kestrel Logistics",
    metrics: [
      { value: "340", label: "seats migrated" },
      { value: "9h → 40m", label: "weekly reporting" },
      { value: "1 quarter", label: "full cutover" },
    ],
  },
  {
    id: "halden",
    mark: HaldenGroup,
    company: "Halden Group",
    industry: "Professional services · 620 staff",
    headline: "Three workspaces became one, in a two-week pilot.",
    body: [
      "Halden had grown by acquisition and inherited three separate workspaces in an engineering-first tool. The delivery teams were fluent in it; the commercial side, which was most of the company, mostly emailed spreadsheets around it.",
      "The pilot was deliberately small: one practice, two weeks, no migration commitment. Templates and a CSV import covered the structure, and the automations that used to be a shared inbox convention became rules on the board.",
      "At the end of the fortnight the three workspaces were consolidated into one, with SSO and audit logs turned on from the Growth plan rather than waiting for an Enterprise contract. The engineering teams kept their repository tooling, which still has the better Git integration; everything downstream of a merge now lives in Vantage.",
    ],
    quote:
      "The pilot was two weeks and we came out of it with three workspaces consolidated into one. The commercial teams needed no training, which was the part I did not believe.",
    attribution: "Marc Vesely · COO, Halden Group",
    metrics: [
      { value: "3 → 1", label: "workspaces" },
      { value: "2 weeks", label: "pilot to production" },
      { value: "620", label: "people on one plan" },
    ],
  },
];

export default function CustomersPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-5 pt-16 pb-8 sm:px-8 sm:pt-20">
      <header className="max-w-3xl">
        <p className="text-xs font-semibold tracking-[0.18em] text-ink-faint uppercase">
          Customers
        </p>
        <h1 className="font-display mt-4 text-5xl leading-[0.98] tracking-tight text-balance sm:text-6xl">
          Two migrations, with the numbers attached.
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-ink-muted">
          Both of these started as a pilot in one team. Neither took a six-week onboarding, and
          in both cases the tool we replaced was doing part of the job well.
        </p>
      </header>

      <div className="mt-16 space-y-16">
        {STORIES.map(({ id, mark: Mark, company, industry, headline, body, quote, attribution, metrics }) => (
          <article
            key={id}
            id={id}
            aria-labelledby={`${id}-heading`}
            className="scroll-mt-24 overflow-hidden rounded-3xl border border-rule bg-paper"
          >
            <div className="grid gap-10 p-8 sm:p-12 lg:grid-cols-[1fr_1.4fr] lg:gap-16">
              <div>
                <Mark className="h-6 text-ink/70" />
                <p className="mt-4 text-sm text-ink-faint">{industry}</p>
                <h2
                  id={`${id}-heading`}
                  className="font-display mt-6 text-4xl leading-[1.05] tracking-tight text-balance"
                >
                  {headline}
                </h2>

                <dl className="mt-8 space-y-5 border-t border-rule pt-6">
                  {metrics.map((metric) => (
                    <div key={metric.label}>
                      {/* Two case studies use the same metric labels, so the accessible
                          name carries the company or the list reads as one set of six. */}
                      <dt className="sr-only">{`${company} — ${metric.label}`}</dt>
                      <dd>
                        <span className="font-display block text-3xl leading-none tracking-tight text-brand">
                          {metric.value}
                        </span>
                        <span className="mt-1.5 block text-xs tracking-wide text-ink-faint uppercase">
                          {metric.label}
                        </span>
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>

              <div>
                {body.map((paragraph) => (
                  <p key={paragraph.slice(0, 32)} className="mt-4 text-[15px] leading-relaxed text-ink-muted first:mt-0">
                    {paragraph}
                  </p>
                ))}

                <figure className="mt-8 rounded-2xl bg-sand/70 p-6 sm:p-8">
                  <IconQuote className="h-5 text-accent" />
                  <blockquote className="font-display mt-4 text-2xl leading-[1.2] tracking-tight text-balance">
                    &ldquo;{quote}&rdquo;
                  </blockquote>
                  <figcaption className="mt-4 text-sm text-ink-muted">{attribution}</figcaption>
                </figure>
              </div>
            </div>
          </article>
        ))}
      </div>

      <section className="mt-16 flex flex-col items-start gap-6 rounded-3xl bg-brand-deep p-8 text-paper sm:p-12 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-3xl leading-tight tracking-tight text-balance sm:text-4xl">
            Yours will look different. Tell us how.
          </h2>
          <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-brand-soft/80">
            Seat count, renewal date, and what you are moving off — that is enough to size a
            pilot. Use the Talk to Sales button in the corner, or start with the plans.
          </p>
        </div>
        <Link
          href="/pricing"
          className="inline-flex shrink-0 items-center gap-2 rounded-full bg-paper px-6 py-3.5 text-sm font-medium text-brand-deep transition-colors hover:bg-brand-soft"
        >
          See pricing
          <IconArrow className="size-4" />
        </Link>
      </section>
    </div>
  );
}
