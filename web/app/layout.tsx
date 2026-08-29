import type { Metadata } from "next";
import Script from "next/script";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
// Instrument Serif ships a single weight; headline contrast comes from size and tracking,
// not from a bold cut that does not exist.
const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
});

const DEMO_AGENT = process.env.NEXT_PUBLIC_DEMO_AGENT_ID ?? "ag_demo";
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const metadata: Metadata = {
  title: {
    default: "Vantage — the system of action for go-to-market teams",
    template: "%s · Vantage",
  },
  description:
    "Vantage is work management for the whole go-to-market org: native automation, live rollups and an open API, live in days rather than a six-week onboarding.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable} h-full antialiased`}
    >
      <body className="grain flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-full focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:text-paper"
        >
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter />

        {/*
          The entire voice integration. This site bundles no widget code, no Agora SDK and
          nothing from the console — if the embed breaks, this page shows it (PRD 10.2).
          The loader injects its own launcher, fixed to the bottom-right of the viewport;
          nothing of ours is placed there.
        */}
        <Script src={`${API}/embed.js?agent=${DEMO_AGENT}`} strategy="afterInteractive" />
      </body>
    </html>
  );
}
