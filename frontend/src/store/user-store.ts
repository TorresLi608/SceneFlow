import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { clearAppQueryCache } from "@/providers/query-provider";
import { useProjectStore } from "@/store/project-store";
import type { AuthUser } from "@/types/auth";

const STORE_KEY = "sceneflow-user-store";

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
        set({ token, user });
      },
      setUser: (user) => set({ user }),
      setHydrated: (hydrated) => set({ hydrated }),
      logout: () => {
        clearAppQueryCache();
        useProjectStore.getState().reset();
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
      },
    }
  )
);
