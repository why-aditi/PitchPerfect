/**
 * The Vantage app, drawn rather than screenshotted. There is no image to ship — the product
 * does not exist — so the hero visual is divs and one inline SVG. It is decorative: the
 * whole thing is a single labelled region so a screen reader gets one sentence instead of
 * forty fragments of fake task text.
 */

const ROWS: { name: string; owner: string; start: number; span: number; tone: string }[] = [
  { name: "Q3 pricing rollout", owner: "GTM", start: 0, span: 46, tone: "bg-brand" },
  { name: "Partner onboarding", owner: "Ops", start: 18, span: 34, tone: "bg-brand/70" },
  { name: "Billing migration", owner: "Eng", start: 30, span: 44, tone: "bg-accent/85" },
  { name: "EMEA launch brief", owner: "Mktg", start: 52, span: 30, tone: "bg-brand/45" },
  { name: "Renewal risk review", owner: "CS", start: 62, span: 26, tone: "bg-ink/25" },
];

const TREND = [18, 26, 22, 34, 31, 44, 41, 56, 62, 58, 71, 80];

export function ProductShot() {
  return (
    <div
      role="img"
      aria-label="The Vantage planner: a delivery timeline for five cross-team workstreams beside a weekly throughput rollup."
      className="overflow-hidden rounded-2xl border border-rule-strong/70 bg-paper shadow-[0_1px_2px_rgba(22,19,15,0.05),0_24px_60px_-30px_rgba(22,19,15,0.35)]"
    >
      <div className="flex items-center gap-3 border-b border-rule bg-sand/70 px-4 py-3">
        <div className="flex gap-1.5" aria-hidden="true">
          <span className="size-2.5 rounded-full bg-rule-strong" />
          <span className="size-2.5 rounded-full bg-rule-strong" />
          <span className="size-2.5 rounded-full bg-rule-strong" />
        </div>
        <div className="ml-1 flex-1 truncate rounded-md bg-paper px-3 py-1 font-mono text-[11px] text-ink-faint">
          app.vantage.com/plan/q3-rollout
        </div>
      </div>

      <div className="grid grid-cols-[auto_1fr] sm:grid-cols-[9.5rem_1fr]">
        <aside className="hidden border-r border-rule px-4 py-5 sm:block">
          <p className="text-[10px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
            Workspace
          </p>
          <ul className="mt-3 space-y-2.5 text-[12px]">
            {["Plan", "Work", "Rollups", "Automations", "Directory"].map((item, i) => (
              <li
                key={item}
                className={
                  i === 0
                    ? "flex items-center gap-2 rounded-md bg-brand-soft px-2 py-1 font-medium text-brand-deep"
                    : "flex items-center gap-2 px-2 py-1 text-ink-muted"
                }
              >
                <span
                  className={`size-1.5 rounded-full ${i === 0 ? "bg-brand" : "bg-rule-strong"}`}
                  aria-hidden="true"
                />
                {item}
              </li>
            ))}
          </ul>
        </aside>

        <div className="min-w-0 px-4 py-5 sm:px-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-semibold">Q3 rollout</p>
            <p className="text-[11px] text-ink-faint">Weeks 27 – 39 · 5 teams</p>
          </div>

          <div className="mt-4 space-y-2.5">
            {ROWS.map((row) => (
              <div key={row.name} className="grid grid-cols-[6.5rem_1fr] items-center gap-3 sm:grid-cols-[9rem_1fr]">
                <div className="min-w-0">
                  <p className="truncate text-[11px] font-medium">{row.name}</p>
                  <p className="text-[10px] text-ink-faint">{row.owner}</p>
                </div>
                <div className="h-3.5 rounded-full bg-sand">
                  <div
                    className={`h-3.5 rounded-full ${row.tone}`}
                    style={{ marginLeft: `${row.start}%`, width: `${row.span}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-5 flex flex-wrap items-end gap-5 border-t border-rule pt-4">
            <div>
              <p className="text-[10px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
                Items shipped / week
              </p>
              <p className="font-display text-3xl leading-none">80</p>
            </div>
            <svg viewBox="0 0 120 34" className="h-9 min-w-32 flex-1" aria-hidden="true">
              <polyline
                points={TREND.map((v, i) => `${(i / (TREND.length - 1)) * 118 + 1},${33 - (v / 90) * 30}`).join(" ")}
                fill="none"
                stroke="var(--color-brand)"
                strokeWidth={1.75}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle
                cx={119}
                cy={33 - (TREND[TREND.length - 1] / 90) * 30}
                r={2.4}
                fill="var(--color-accent)"
              />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}
