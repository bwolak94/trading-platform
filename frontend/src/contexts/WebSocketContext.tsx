/**
 * WebSocketContext — provides a single shared WebSocket connection to the
 * entire component tree.
 *
 * Instead of every component instantiating its own hook, they consume this
 * context and subscribe to specific typed channels.  This eliminates the
 * duplicate-connection bug that arose when multiple components each called
 * useWebSocket() independently.
 *
 * Usage:
 *   // Wrap the app once (done in App.tsx)
 *   <WebSocketProvider><App /></WebSocketProvider>
 *
 *   // In any component:
 *   const { isConnected, subscribe, unsubscribe, useChannelMessage } = useWebSocketContext();
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { WSMessage } from "../types";

interface WebSocketContextValue {
  isConnected: boolean;
  subscribe: (channels: string[]) => void;
  unsubscribe: (channels: string[]) => void;
  /** Returns the latest message for a specific channel type, or null. */
  lastMessageByType: (type: WSMessage["type"]) => WSMessage | null;
  /** Full batch of messages received in the last 100 ms flush. */
  lastBatch: WSMessage[];
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

const WS_URL =
  (window.location.protocol === "https:" ? "wss://" : "ws://") +
  window.location.host +
  "/ws";

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000];

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastBatch, setLastBatch] = useState<WSMessage[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const mountedRef = useRef(true);
  const channelsRef = useRef<Set<string>>(new Set());
  const bufferRef = useRef<WSMessage[]>([]);
  // Index of last message per type for O(1) lookup
  const latestByTypeRef = useRef<Map<string, WSMessage>>(new Map());

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      retriesRef.current = 0;
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
        bufferRef.current.push(data);
        latestByTypeRef.current.set(data.type, data);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      if (!mountedRef.current) return;
      const delay =
        RECONNECT_DELAYS[Math.min(retriesRef.current, RECONNECT_DELAYS.length - 1)] ??
        RECONNECT_DELAYS[RECONNECT_DELAYS.length - 1]!;
      retriesRef.current += 1;
      setTimeout(connect, delay);
    };

    ws.onerror = () => { ws.close(); };
  }, []);

  // Flush the message buffer every 100 ms — single batch state update
  useEffect(() => {
    const id = setInterval(() => {
      if (bufferRef.current.length === 0) return;
      const batch = bufferRef.current;
      bufferRef.current = [];
      setLastBatch(batch);
    }, 100);
    return () => { clearInterval(id); };
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
      wsRef.current.send(JSON.stringify({ action: "subscribe", channels }));
    }
  }, []);

  const unsubscribe = useCallback((channels: string[]) => {
    channels.forEach((c) => channelsRef.current.delete(c));
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "unsubscribe", channels }));
    }
  }, []);

  const lastMessageByType = useCallback(
    (type: WSMessage["type"]): WSMessage | null =>
      latestByTypeRef.current.get(type) ?? null,
    [],
  );

  return (
    <WebSocketContext.Provider
      value={{ isConnected, subscribe, unsubscribe, lastMessageByType, lastBatch }}
    >
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocketContext(): WebSocketContextValue {
  const ctx = useContext(WebSocketContext);
  if (!ctx) {
    throw new Error("useWebSocketContext must be used inside <WebSocketProvider>");
  }
  return ctx;
}
