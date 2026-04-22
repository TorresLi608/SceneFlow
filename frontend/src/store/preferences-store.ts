"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type AppLocale = "zh" | "en";
export type AppTheme = "light" | "dark";

const STORE_KEY = "sceneflow-preferences-store";

interface PreferencesStoreState {
  locale: AppLocale;
  theme: AppTheme;
  hydrated: boolean;
  setLocale: (locale: AppLocale) => void;
  setTheme: (theme: AppTheme) => void;
  toggleLocale: () => void;
  toggleTheme: () => void;
  setHydrated: (hydrated: boolean) => void;
}

export const usePreferencesStore = create<PreferencesStoreState>()(
  persist(
    (set, get) => ({
      locale: "zh",
      theme: "dark",
      hydrated: false,
      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
      toggleLocale: () => set({ locale: get().locale === "zh" ? "en" : "zh" }),
      toggleTheme: () => set({ theme: get().theme === "dark" ? "light" : "dark" }),
      setHydrated: (hydrated) => set({ hydrated }),
    }),
    {
      name: STORE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        locale: state.locale,
        theme: state.theme,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
      },
    }
  )
);
