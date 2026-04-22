import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { cn } from "@/lib/utils";
import { AppPreferencesProvider } from "@/providers/app-preferences-provider";
import { QueryProvider } from "@/providers/query-provider";

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
  title: "SceneFlow",
  description: "AI 漫剧可视化工作台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className={cn(geistSans.variable, geistMono.variable, "h-full antialiased")}>
      <body className="min-h-full flex flex-col">
        <AppPreferencesProvider>
          <QueryProvider>{children}</QueryProvider>
        </AppPreferencesProvider>
      </body>
    </html>
  );
}
