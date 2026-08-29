import Link from "next/link";

const COLUMNS: { heading: string; links: { label: string; href: string }[] }[] = [
  {
    heading: "Product",
    links: [
      { label: "Overview", href: "/product" },
      { label: "Automations", href: "/product#automations" },
      { label: "Rollups", href: "/product#rollups" },
      { label: "Pricing", href: "/pricing" },
    ],
  },
  {
    heading: "Company",
    links: [
      { label: "Customers", href: "/customers" },
      { label: "Kestrel Logistics", href: "/customers#kestrel" },
      { label: "Halden Group", href: "/customers#halden" },
    ],
  },
];

export function SiteFooter() {
  return (
    // The embed's launcher pins itself to the bottom-right of the viewport, so this footer
    // keeps its right column short and carries extra bottom padding: nothing of ours should
    // sit under the button a prospect is meant to click.
    <footer className="mt-24 border-t border-rule bg-sand/50">
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-5 pt-14 pb-24 sm:px-8 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <div className="flex items-center gap-2.5 font-semibold tracking-tight">
            <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5 text-brand">
              <path d="M12 6.5 18.5 19.5h-13L12 6.5Z" fill="currentColor" />
            </svg>
            Vantage
          </div>
          <p className="mt-3 max-w-xs text-sm text-ink-muted">
            Work management for the whole go-to-market org. Plan, deliver and report in one
            place, without a reporting project on the side.
          </p>
        </div>

        {COLUMNS.map((col) => (
          <nav key={col.heading} aria-label={col.heading}>
            <h2 className="text-[11px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
              {col.heading}
            </h2>
            <ul className="mt-4 space-y-2.5 text-sm">
              {col.links.map((link) => (
                <li key={link.label}>
                  <Link href={link.href} className="text-ink-muted transition-colors hover:text-ink">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>

      <div className="border-t border-rule">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-5 py-6 pb-24 text-xs text-ink-faint sm:px-8 md:flex-row md:items-start md:justify-between md:pb-10">
          <p>© {new Date().getFullYear()} Vantage Software, Inc. A fictional company, built for a product demo.</p>
          {/* PRD 11 requires the AI disclosure at the start of a call. Saying it on the page as
              well means a visitor knows before they press the button, not after. */}
          <p className="max-w-md md:text-right">
            Sales calls placed from the Talk to Sales button on this site are handled by an AI
            assistant, and the conversation is transcribed. Ask for a human at any point and
            the call is passed to a rep on the same line.
          </p>
        </div>
      </div>
    </footer>
  );
}
