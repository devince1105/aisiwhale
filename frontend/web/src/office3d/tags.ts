// Whether the office shows the name tags over the seats (D-123). They can hide what is behind
// them — a window, a shelf — so a viewer may turn them off; a per-viewer convenience, remembered
// in this browser (localStorage) like the style, and on by default.
import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";

export const TAGS_STORAGE_KEY = "autora.officeTags";

function readTags(): boolean {
  try {
    return typeof window === "undefined" || window.localStorage.getItem(TAGS_STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

export const tagsStore = createStore<{ shown: boolean; show: (shown: boolean) => void }>()((set) => ({
  shown: readTags(),
  show: (shown) => {
    set({ shown });
    try {
      window.localStorage.setItem(TAGS_STORAGE_KEY, shown ? "on" : "off");
    } catch {
      // not remembered; the choice still applies until the page is left
    }
  },
}));

export function useTagsShown(): [boolean, (shown: boolean) => void] {
  return [useStore(tagsStore, (s) => s.shown), useStore(tagsStore, (s) => s.show)];
}
