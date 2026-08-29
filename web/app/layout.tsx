import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Vantage — work management",
  description: "PitchPilot demo site",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="flex items-center justify-between border-b border-neutral-200 px-6 py-4 dark:border-neutral-800">
          <Link href="/" className="font-semibold">
            Vantage
          </Link>
          <nav className="flex gap-4 text-sm text-neutral-500">
            <Link href="/dashboard">Dashboard</Link>
            <Link href="/rep">Rep view</Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
