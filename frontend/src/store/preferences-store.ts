"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type AppLocale = "zh" | "en";
export type AppTheme = "light" | "dark";

const STORE_KEY = "sceneflow-preferences-store";

interface PreferencesStoreState {
  locale: AppLocale;
  theme: AppTheme;
  sidebarCollapsed: boolean;
  workbenchSidebarCollapsed: boolean;
  hydrated: boolean;
  setLocale: (locale: AppLocale) => void;
  setTheme: (theme: AppTheme) => void;
  toggleLocale: () => void;
  toggleTheme: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebarCollapsed: () => void;
  setWorkbenchSidebarCollapsed: (collapsed: boolean) => void;
  toggleWorkbenchSidebarCollapsed: () => void;
  setHydrated: (hydrated: boolean) => void;
}

export const usePreferencesStore = create<PreferencesStoreState>()(
  persist(
    (set, get) => ({
      locale: "zh",
      theme: "dark",
      sidebarCollapsed: false,
      workbenchSidebarCollapsed: false,
      hydrated: false,
      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
      toggleLocale: () => set({ locale: get().locale === "zh" ? "en" : "zh" }),
      toggleTheme: () => set({ theme: get().theme === "dark" ? "light" : "dark" }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebarCollapsed: () => set({ sidebarCollapsed: !get().sidebarCollapsed }),
      setWorkbenchSidebarCollapsed: (workbenchSidebarCollapsed) => set({ workbenchSidebarCollapsed }),
      toggleWorkbenchSidebarCollapsed: () =>
        set({ workbenchSidebarCollapsed: !get().workbenchSidebarCollapsed }),
      setHydrated: (hydrated) => set({ hydrated }),
    }),
    {
      name: STORE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        locale: state.locale,
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
        workbenchSidebarCollapsed: state.workbenchSidebarCollapsed,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
      },
    }
  )
);
