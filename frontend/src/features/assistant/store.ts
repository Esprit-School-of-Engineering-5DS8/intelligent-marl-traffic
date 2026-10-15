import { create } from "zustand";

import type { ToolCall } from "@/shared/schemas";

export interface ToolState {
  id: string;
  call: ToolCall;
  status: "proposed" | "confirmed" | "cancelled";
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  tools: ToolState[];
  sources: string[];
  writtenBy?: "model" | "code";
  error?: string;
  streaming?: boolean;
}

interface ChatStore {
  messages: Message[];
  add: (message: Message) => void;
  update: (id: string, change: (m: Message) => Message) => void;
  clear: () => void;
}

/** The conversation, kept while the app is open (the panel and the page share it). */
export const useChat = create<ChatStore>()((set) => ({
  messages: [],
  add: (message) => set((s) => ({ messages: [...s.messages, message] })),
  update: (id, change) =>
    set((s) => ({ messages: s.messages.map((m) => (m.id === id ? change(m) : m)) })),
  clear: () => set({ messages: [] }),
}));

let counter = 0;
export const newId = () => `m${Date.now().toString(36)}${(counter++).toString(36)}`;
