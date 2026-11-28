import { AppProviders } from "@dijione/design-system";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AtworkShell } from "./atwork-shell";
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
  title: "DijiAtWork — by Dijital Team",
  description: "Manage your workday, your time and your requests—all in one place.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-dt-background text-dt-text-primary">
        <AppProviders>
          <AtworkShell>{children}</AtworkShell>
        </AppProviders>
      </body>
    </html>
  );
}
