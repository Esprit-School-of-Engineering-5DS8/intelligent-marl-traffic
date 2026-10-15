import type { StateStorage } from "zustand/middleware";

/**
 * localStorage that never throws: private windows, blocked site data or a full quota make
 * the browser refuse it, and the dashboard must still work (settings are then per session).
 */
export const safeStorage: StateStorage = {
  getItem: (name) => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      window.localStorage.setItem(name, value);
    } catch {
      /* not persisted: kept in memory for this session */
    }
  },
  removeItem: (name) => {
    try {
      window.localStorage.removeItem(name);
    } catch {
      /* nothing to remove */
    }
  },
};
