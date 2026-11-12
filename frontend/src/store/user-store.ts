import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { clearAppQueryCache } from "@/providers/query-provider";
import { useProjectStore } from "@/store/project-store";
import type { AuthUser } from "@/types/auth";

const STORE_KEY = "sceneflow-user-store";

function syncRoleCookie(role: string | null | undefined) {
  if (typeof document === "undefined") return;
  if (role) {
    document.cookie = `sceneflow-role=${encodeURIComponent(role)}; path=/; max-age=604800; SameSite=Lax`;
  } else {
    document.cookie = "sceneflow-role=; path=/; max-age=0; SameSite=Lax";
  }
}

interface UserStoreState {
  token: string | null;
  user: AuthUser | null;
  hydrated: boolean;
  setAuth: (token: string, user: AuthUser) => void;
  setUser: (user: AuthUser | null) => void;
  setHydrated: (hydrated: boolean) => void;
  logout: () => void;
}

export const useUserStore = create<UserStoreState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      hydrated: false,
      setAuth: (token, user) => {
        clearAppQueryCache();
        useProjectStore.getState().reset();
        syncRoleCookie(user.role);
        set({ token, user });
      },
      setUser: (user) => {
        syncRoleCookie(user?.role);
        set({ user });
      },
      setHydrated: (hydrated) => set({ hydrated }),
      logout: () => {
        clearAppQueryCache();
        useProjectStore.getState().reset();
        syncRoleCookie(null);
        set({ token: null, user: null });
      },
    }),
    {
      name: STORE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        token: state.token,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
        if (state?.user?.role) {
          syncRoleCookie(state.user.role);
        }
      },
    }
  )
);
