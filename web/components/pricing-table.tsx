import { IconCheck } from "@/components/icons";
import type { Pricing, Tier } from "@/lib/types";

/** The currency code comes from the agent's config rather than from us, so an unrecognised
 *  code must degrade to something readable instead of throwing on the server. */
function money(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

function seatRange(tier: Tier) {
  return tier.max_seats === null
    ? `${tier.min_seats}+ seats`
    : `${tier.min_seats}–${tier.max_seats} seats`;
}

export function PricingTable({ pricing }: { pricing: Pricing }) {
  // Which plan gets the visual emphasis is positional, not stored. The pricing config the
  // agent quotes from has no notion of a "recommended" tier, and inventing one here would
  // put the page a step ahead of what the agent can say on the call.
  const featured = pricing.tiers.length >= 3 ? 1 : -1;

  return (
    <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
      {pricing.tiers.map((tier, i) => {
        const isFeatured = i === featured;
        return (
          <article
            key={tier.name}
            className={`flex flex-col rounded-2xl border p-6 sm:p-7 ${
              isFeatured
                ? "border-brand bg-brand-deep text-paper shadow-[0_24px_60px_-32px_rgba(8,46,41,0.7)]"
                : "border-rule bg-paper"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className={`text-sm font-semibold tracking-[0.14em] uppercase ${isFeatured ? "text-brand-soft" : "text-ink-muted"}`}>
                {tier.name}
              </h3>
              {isFeatured && (
                <span className="rounded-full bg-accent px-2.5 py-1 text-[10px] font-semibold tracking-[0.1em] text-paper uppercase">
                  Most teams
                </span>
              )}
            </div>

            <p className="mt-5 flex items-baseline gap-1.5">
              <span className="font-display text-5xl leading-none tracking-tight">
                {money(tier.per_seat_month, pricing.currency)}
              </span>
              <span className={`text-sm ${isFeatured ? "text-brand-soft/80" : "text-ink-muted"}`}>
                /seat/mo
              </span>
            </p>

            <p className={`mt-2 text-sm ${isFeatured ? "text-brand-soft/85" : "text-ink-muted"}`}>
              {seatRange(tier)}
            </p>

            {/* Not every tier has a volume break, and the top tier has no seat ceiling. Both
                gaps are rendered rather than hidden — a prospect who hears about the break on
                the call needs to find it on the page. */}
            <p
              className={`mt-4 rounded-lg border px-3 py-2.5 text-[13px] ${
                tier.volume_break
                  ? isFeatured
                    ? "border-brand-soft/25 bg-paper/10 text-brand-soft"
                    : "border-accent/25 bg-accent-soft text-accent"
                  : isFeatured
                    ? "border-brand-soft/20 text-brand-soft/70"
                    : "border-rule text-ink-faint"
              }`}
            >
              {tier.volume_break ? (
                <>
                  Volume break:{" "}
                  <strong className="font-semibold">
                    {money(tier.volume_break.per_seat_month, pricing.currency)}/seat
                  </strong>{" "}
                  from {tier.volume_break.seats} seats.
                </>
              ) : (
                <>Flat rate — no volume break on this plan.</>
              )}
            </p>

            <ul className="mt-6 flex-1 space-y-2.5 text-sm">
              {tier.features.map((feature) => (
                <li key={feature} className="flex gap-2.5">
                  <IconCheck
                    className={`mt-0.5 size-4 shrink-0 ${isFeatured ? "text-accent" : "text-brand"}`}
                  />
                  <span className={isFeatured ? "text-brand-soft" : "text-ink-muted"}>{feature}</span>
                </li>
              ))}
            </ul>

            <p
              className={`mt-7 border-t pt-4 text-xs ${
                isFeatured ? "border-brand-soft/20 text-brand-soft/70" : "border-rule text-ink-faint"
              }`}
            >
              Billed annually. Talk to sales for a quote at {seatRange(tier).toLowerCase()}.
            </p>
          </article>
        );
      })}
    </div>
  );
}
