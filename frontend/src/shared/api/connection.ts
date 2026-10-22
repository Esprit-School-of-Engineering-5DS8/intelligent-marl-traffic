import { create } from "zustand";

export type ConnectionStatus = "offline" | "connecting" | "online";

interface ConnectionStore {
  status: ConnectionStatus;
  setStatus: (status: ConnectionStatus) => void;
}

/** State of the real-time stream; the WebSocket client (live source) writes it. */
export const useConnection = create<ConnectionStore>()((set) => ({
  status: "offline",
  setStatus: (status) => set({ status }),
}));
