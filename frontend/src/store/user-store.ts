import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { AuthUser, ModelOption } from "@/types/auth";

const STORE_KEY = "sceneflow-user-store";

interface UserStoreState {
  token: string | null;
  user: AuthUser | null;
  selectedModel: ModelOption;
  hydrated: boolean;
  setAuth: (token: string, user: AuthUser) => void;
  setUser: (user: AuthUser | null) => void;
  setSelectedModel: (model: ModelOption) => void;
  setHydrated: (hydrated: boolean) => void;
  logout: () => void;
}

export const useUserStore = create<UserStoreState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      selectedModel: "gpt-4o",
      hydrated: false,
      setAuth: (token, user) => set({ token, user }),
      setUser: (user) => set({ user }),
      setSelectedModel: (selectedModel) => set({ selectedModel }),
      setHydrated: (hydrated) => set({ hydrated }),
      logout: () => set({ token: null, user: null, selectedModel: "gpt-4o" }),
    }),
    {
      name: STORE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        selectedModel: state.selectedModel,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
      },
    }
  )
);
