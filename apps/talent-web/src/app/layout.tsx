import { AppProviders } from "@dijione/design-system";
import type { Metadata } from "next";
import { Be_Vietnam_Pro, Geist_Mono } from "next/font/google";
import { TalentShell } from "./talent-shell";
import "./globals.css";

// Official Dijital Team supporting font (docs/talent-flow/brand-baseline.md
// §C) — the guideline shows Light/Bold; 300-700 covers every weight this
// app actually uses.
const beVietnamPro = Be_Vietnam_Pro({
  variable: "--font-be-vietnam-pro",
  subsets: ["latin"],
  weight: ["300", "400", "600", "700"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DijiTalentFlow — by Dijital Team",
  description: "Talent Operations and Client Tracking.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${beVietnamPro.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-dt-background text-dt-text-primary">
        <AppProviders>
          <TalentShell>{children}</TalentShell>
        </AppProviders>
      </body>
    </html>
  );
}
