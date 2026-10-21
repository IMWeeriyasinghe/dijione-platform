import { AppProviders } from "@dijione/design-system";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { OnsiteShell } from "./onsite-shell";
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
  title: "Diji On-site — by Dijital Team",
  description: "On-site Attendance Operations.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-dt-background text-dt-text-primary">
        <AppProviders>
          <OnsiteShell>{children}</OnsiteShell>
        </AppProviders>
      </body>
    </html>
  );
}
