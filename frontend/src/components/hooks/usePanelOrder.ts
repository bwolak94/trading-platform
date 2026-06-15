/**
 * usePanelOrder — manages the ordering of Dashboard panels.
 *
 * Persists the panel order in localStorage under the key
 * "dashboard-panel-order". Exposes helpers to move a panel up/down
 * and reset to the default order.
 */

import { useCallback, useState } from "react";

export type PanelId =
  | "chart"
  | "live-regime"
  | "market-overview"
  | "macro-sector"
  | "market-sentiment"
  | "market-intelligence"
  | "correlation-funding"
  | "heatmaps"
  | "analysis"
  | "simulation"
  | "analytics"
  | "trade-duration-timing"
  | "attribution"
  | "exposure-heatmap"
  | "funding-heatmap"
  | "live-readiness"
  | "signal-history"
  | "notification-history"
  | "signals-risk";

export const DEFAULT_PANEL_ORDER: PanelId[] = [
  "chart",
  "live-regime",
  "market-overview",
  "macro-sector",
  "market-sentiment",
  "market-intelligence",
  "correlation-funding",
  "heatmaps",
  "analysis",
  "simulation",
  "analytics",
  "trade-duration-timing",
  "attribution",
  "exposure-heatmap",
  "funding-heatmap",
  "live-readiness",
  "signal-history",
  "notification-history",
  "signals-risk",
];

const STORAGE_KEY = "dashboard-panel-order";

function loadOrder(): PanelId[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PANEL_ORDER;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return DEFAULT_PANEL_ORDER;
    // Only keep IDs that are still valid; append any new ones at the end
    const stored = parsed.filter((id): id is PanelId =>
      DEFAULT_PANEL_ORDER.includes(id as PanelId),
    );
    const missing = DEFAULT_PANEL_ORDER.filter((id) => !stored.includes(id));
    return [...stored, ...missing];
  } catch {
    return DEFAULT_PANEL_ORDER;
  }
}

function saveOrder(order: PanelId[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(order));
  } catch {
    // ignore
  }
}

export function usePanelOrder() {
  const [order, setOrder] = useState<PanelId[]>(loadOrder);

  const moveUp = useCallback((id: PanelId) => {
    setOrder((prev) => {
      const idx = prev.indexOf(id);
      if (idx <= 0) return prev;
      const next = [...prev];
      [next[idx - 1], next[idx]] = [next[idx]!, next[idx - 1]!];
      saveOrder(next);
      return next;
    });
  }, []);

  const moveDown = useCallback((id: PanelId) => {
    setOrder((prev) => {
      const idx = prev.indexOf(id);
      if (idx < 0 || idx >= prev.length - 1) return prev;
      const next = [...prev];
      [next[idx], next[idx + 1]] = [next[idx + 1]!, next[idx]!];
      saveOrder(next);
      return next;
    });
  }, []);

  const resetLayout = useCallback(() => {
    saveOrder(DEFAULT_PANEL_ORDER);
    setOrder([...DEFAULT_PANEL_ORDER]);
  }, []);

  return { order, moveUp, moveDown, resetLayout };
}
