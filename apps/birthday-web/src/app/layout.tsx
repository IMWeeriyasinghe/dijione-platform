import { AppProviders } from "@dijione/design-system";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { BirthdayShell } from "./birthday-shell";
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
  title: "DijiBirthday — by Dijital Team",
  description: "Birthday Workflow Automation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-dt-background text-dt-text-primary">
        <AppProviders>
          <BirthdayShell>{children}</BirthdayShell>
        </AppProviders>
      </body>
    </html>
  );
}
