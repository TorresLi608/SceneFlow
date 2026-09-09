import { create } from "zustand";

/**
 * Store to track unsaved project settings (model config or production settings).
 * The info page sets this when the user edits settings, and clears it on save.
 * The episode page checks this before generating to warn the user.
 */
interface UnsavedSettingsState {
  /** Map of projectId -> boolean indicating if that project has unsaved settings */
  unsavedByProject: Record<string, boolean>;

  /** Mark a project as having unsaved settings */
  markUnsaved: (projectId: string) => void;

  /** Mark a project as having all settings saved */
  markSaved: (projectId: string) => void;

  /** Check if a project has unsaved settings */
  hasUnsaved: (projectId: string) => boolean;

  /** Clear all unsaved flags */
  reset: () => void;
}

export const useUnsavedSettingsStore = create<UnsavedSettingsState>()((set, get) => ({
  unsavedByProject: {},

  markUnsaved: (projectId) => {
    set((state) => ({
      unsavedByProject: {
        ...state.unsavedByProject,
        [projectId]: true,
      },
    }));
  },

  markSaved: (projectId) => {
    set((state) => ({
      unsavedByProject: {
        ...state.unsavedByProject,
        [projectId]: false,
      },
    }));
  },

  hasUnsaved: (projectId) => {
    return Boolean(get().unsavedByProject[projectId]);
  },

  reset: () => {
    set({ unsavedByProject: {} });
  },
}));
