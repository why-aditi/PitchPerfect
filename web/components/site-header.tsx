"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/product", label: "Product" },
  { href: "/customers", label: "Customers" },
  { href: "/pricing", label: "Pricing" },
];

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-ground/85 backdrop-blur-md">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-4 px-5 py-3.5 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
          <svg viewBox="0 0 24 24" aria-hidden="true" className="size-6 text-brand">
            <path d="M12 1.5 22.5 22.5H1.5L12 1.5Z" fill="currentColor" opacity={0.18} />
            <path d="M12 6.5 18.5 19.5h-13L12 6.5Z" fill="currentColor" />
          </svg>
          <span className="text-[17px]">Vantage</span>
        </Link>

        <nav aria-label="Primary" className="ml-auto flex items-center gap-1 text-sm">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-full px-3 py-1.5 transition-colors ${
                  active
                    ? "bg-brand-soft font-medium text-brand-deep"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <Link
          href="/pricing"
          className="hidden rounded-full bg-brand px-4 py-2 text-sm font-medium text-paper transition-colors hover:bg-brand-deep sm:inline-block"
        >
          See plans
        </Link>
      </div>
    </header>
  );
}
