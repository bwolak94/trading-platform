import { useCallback, useEffect, useRef, useState } from "react";
import type { WSMessage } from "../types";

const WS_URL =
  (window.location.protocol === "https:" ? "wss://" : "ws://") +
  window.location.host +
  "/ws";

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000];

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WSMessage | null;
  subscribe: (channels: string[]) => void;
  unsubscribe: (channels: string[]) => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const mountedRef = useRef(true);
  const channelsRef = useRef<Set<string>>(new Set());

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      retriesRef.current = 0;

      // Resubscribe to any channels from before reconnect
      if (channelsRef.current.size > 0) {
        ws.send(
          JSON.stringify({
            action: "subscribe",
            channels: Array.from(channelsRef.current),
          }),
        );
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSMessage;
        setLastMessage(data);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;

      if (!mountedRef.current) return;

      const delay =
        RECONNECT_DELAYS[
          Math.min(retriesRef.current, RECONNECT_DELAYS.length - 1)
        ] ?? RECONNECT_DELAYS[RECONNECT_DELAYS.length - 1]!;
      retriesRef.current += 1;
      setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
    };
  }, [connect]);

  const subscribe = useCallback((channels: string[]) => {
    channels.forEach((c) => channelsRef.current.add(c));
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ action: "subscribe", channels }),
      );
    }
  }, []);

  const unsubscribe = useCallback((channels: string[]) => {
    channels.forEach((c) => channelsRef.current.delete(c));
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ action: "unsubscribe", channels }),
      );
    }
  }, []);

  return { isConnected, lastMessage, subscribe, unsubscribe };
}
