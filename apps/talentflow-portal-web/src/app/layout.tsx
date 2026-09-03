import type { Metadata } from "next";
import { Be_Vietnam_Pro, Geist_Mono } from "next/font/google";

import { AppShell } from "./app-shell";
import "./globals.css";

// Official Dijital Team supporting font (docs/talent-flow/brand-baseline.md
// §C) — highest-priority surface to align, per the baseline, since this is
// the external client-facing app.
const beVietnamPro = Be_Vietnam_Pro({
  variable: "--font-be-vietnam-pro",
  subsets: ["latin"],
  weight: ["300", "400", "600", "700"],
});
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Client Talent Review Workspace",
  description:
    "Review the candidates and progress for your talent engagement with Dijital Team.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${beVietnamPro.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-dt-background text-dt-text-primary">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
