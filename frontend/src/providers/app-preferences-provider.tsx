"use client";

import { useEffect } from "react";

import { usePreferencesStore } from "@/store/preferences-store";

export function AppPreferencesProvider({ children }: { children: React.ReactNode }) {
  const locale = usePreferencesStore((state) => state.locale);
  const theme = usePreferencesStore((state) => state.theme);

  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return <>{children}</>;
}
