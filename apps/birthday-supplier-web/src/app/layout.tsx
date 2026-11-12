import type { Metadata } from "next";
import { Be_Vietnam_Pro, Geist_Mono } from "next/font/google";
import { AppShell } from "./app-shell";
import "./globals.css";

// Official Dijital Team supporting font (Phase 1.6 §18 — docs/talent-flow/
// brand-baseline.md §C), mirroring talent-web's registration exactly. The
// guideline shows Light/Bold; 300-700 covers every weight this app uses.
const beVietnamPro = Be_Vietnam_Pro({
  variable: "--font-be-vietnam-pro",
  subsets: ["latin"],
  weight: ["300", "400", "600", "700"],
});
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "DijiBirthday Supplier Portal — by Dijital Team",
  description: "Fulfilment view for birthday cake orders assigned to your business.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${beVietnamPro.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-dt-background text-dt-text-primary">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
