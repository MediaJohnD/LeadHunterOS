import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import "@/brand/globals.css";
import { AppProviders } from "@/app/providers";
import { AppShell } from "@/components/layout/app-shell";

const leadHunterSans = localFont({
  src: "../public/fonts/segoeui.ttf",
  variable: "--font-leadhunter-sans",
  display: "swap",
});

const leadHunterMono = localFont({
  src: "../public/fonts/consola.ttf",
  variable: "--font-leadhunter-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "LeadHunterOS",
  description: "LeadHunterOS executive operations dashboard",
  applicationName: "LeadHunterOS",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${leadHunterSans.variable} ${leadHunterMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AppProviders>
          <AppShell>{children}</AppShell>
        </AppProviders>
      </body>
    </html>
  );
}
