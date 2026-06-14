/**
 * useWebSocket — backwards-compatible hook that delegates to WebSocketContext.
 *
 * Existing components that import useWebSocket continue to work unchanged.
 * New components should prefer useWebSocketContext() directly for richer
 * per-channel subscriptions and batch message access.
 *
 * NOTE: This hook only exposes the last message in the batch to preserve the
 * existing interface.  For use-cases that must process every message (e.g.
 * order-book updates, liquidation events), consume lastBatch from
 * useWebSocketContext() instead.
 */

import { useWebSocketContext } from "../contexts/WebSocketContext";
import type { WSMessage } from "../types";

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WSMessage | null;
  /** Full batch of messages received in the last 100 ms flush. */
  lastBatch: WSMessage[];
  subscribe: (channels: string[]) => void;
  unsubscribe: (channels: string[]) => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const { isConnected, subscribe, unsubscribe, lastBatch } =
    useWebSocketContext();

  // Derive the "last message" as the most recent item in the batch for
  // backwards compat.  Components that only care about one message type should
  // call lastMessageByType(type) directly via useWebSocketContext().
  const lastMessage = lastBatch.length > 0
    ? lastBatch[lastBatch.length - 1] ?? null
    : null;

  return { isConnected, lastMessage, lastBatch, subscribe, unsubscribe };
}
