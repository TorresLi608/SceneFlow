import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Toaster } from "@/components/ui/toast";
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
  description: "AI manga storyboard workspace",
};

/** Inline script to prevent theme flashing during SSR and initial page load */
const THEME_INITIALIZER_SCRIPT = `
(function() {
  try {
    var stored = localStorage.getItem("sceneflow-preferences-store");
    var theme = "dark";
    if (stored) {
      var parsed = JSON.parse(stored);
      if (parsed && parsed.state && parsed.state.theme) {
        theme = parsed.state.theme;
      }
    }
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  } catch (e) {
    document.documentElement.classList.add("dark");
  }
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      suppressHydrationWarning
      className={cn(geistSans.variable, geistMono.variable, "h-full antialiased dark")}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INITIALIZER_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <AppPreferencesProvider>
          <QueryProvider>
            <Toaster>{children}</Toaster>
          </QueryProvider>
        </AppPreferencesProvider>
      </body>
    </html>
  );
}
