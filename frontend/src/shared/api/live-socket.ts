import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { useSettings } from "@/features/settings/store";

import { useConnection } from "./connection";

const MAX_DELAY_MS = 30_000;

/**
 * Keeps a WebSocket to the backend while the live source is selected: drives the status
 * badge and refreshes the runs when they change. Reconnects with exponential backoff
 * (1 s, 2 s, 4 s... up to 30 s, with jitter) after any disconnection.
 */
export function useLiveSocket(): void {
  const live = useSettings((s) => s.dataSource) === "live";
  const setStatus = useConnection((s) => s.setStatus);
  const client = useQueryClient();

  useEffect(() => {
    if (!live) {
      setStatus("offline");
      return;
    }
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let stopped = false;

    const connect = () => {
      setStatus("connecting");
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}/ws/status`);
      socket.onopen = () => {
        attempt = 0;
        setStatus("online");
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(String(event.data)) as { type?: string };
          if (message.type === "runs") void client.invalidateQueries({ queryKey: ["runs"] });
        } catch {
          /* not JSON: ignored */
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        setStatus("offline");
        const delay = Math.min(MAX_DELAY_MS, 1000 * 2 ** attempt) * (0.75 + Math.random() * 0.5);
        attempt += 1;
        timer = setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
      setStatus("offline");
    };
  }, [live, setStatus, client]);
}
