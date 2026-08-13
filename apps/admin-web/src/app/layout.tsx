import { AppProviders } from "@dijione/design-system";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AdminShell } from "./admin-shell";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DijiOne Admin Center — by Dijital Team",
  description: "Centralized identity, authorization and module administration for DijiOne.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      {/*
        suppressHydrationWarning is scoped to this single element only, and
        only silences *attribute* mismatches on <body> itself (not its
        subtree). It's here because browser extensions like Grammarly inject
        data-new-gr-c-s-check-loaded / data-gr-ext-installed onto <body>
        before React hydrates, which is a known false-positive source, not a
        real rendering bug — see docs/platform/admin-center.md "Hydration
        warning investigation" for the verification that ruled out a genuine
        mismatch.
      */}
      <body className="min-h-full flex flex-col bg-dt-background text-dt-text-primary" suppressHydrationWarning>
        <AppProviders>
          <AdminShell>{children}</AdminShell>
        </AppProviders>
      </body>
    </html>
  );
}
