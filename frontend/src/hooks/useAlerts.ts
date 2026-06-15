import { useCallback, useEffect, useRef, useState } from "react";

// --- Types ---

type AlertCondition =
  | "price_above"
  | "price_below"
  | "rsi_above"
  | "rsi_below"
  | "new_signal";

interface AlertRule {
  readonly id: string;
  readonly asset: string;
  readonly condition: AlertCondition;
  readonly value: number;
  enabled: boolean;
  triggered: boolean;
  triggeredAt: string | null;
}

interface MarketDataPoint {
  readonly asset: string;
  readonly price: number;
  readonly rsi?: number;
  readonly hasNewSignal?: boolean;
}

interface UseAlertsReturn {
  readonly alerts: readonly AlertRule[];
  addAlert: (
    asset: string,
    condition: AlertCondition,
    value: number,
  ) => void;
  removeAlert: (id: string) => void;
  toggleAlert: (id: string) => void;
  clearTriggered: () => void;
  checkAlerts: (currentData: MarketDataPoint[]) => void;
  readonly triggeredAlerts: readonly AlertRule[];
}

// --- Constants ---

const STORAGE_KEY = "trading_alert_rules";

// --- Helpers ---

function generateId(): string {
  return `alert_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function loadAlerts(): AlertRule[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    return parsed as AlertRule[];
  } catch {
    return [];
  }
}

function persistAlerts(alerts: readonly AlertRule[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch {
    // Storage full or unavailable - silently ignore
  }
}

function requestNotificationPermission(): void {
  if (typeof Notification === "undefined") return;
  if (Notification.permission === "default") {
    void Notification.requestPermission();
  }
}

function sendBrowserNotification(title: string, body: string): void {
  if (typeof Notification === "undefined") return;
  if (Notification.permission !== "granted") return;

  new Notification(title, {
    body,
    icon: "/favicon.ico",
    tag: `alert-${Date.now()}`,
  });
}

function evaluateCondition(
  rule: AlertRule,
  data: MarketDataPoint,
): boolean {
  switch (rule.condition) {
    case "price_above":
      return data.price > rule.value;
    case "price_below":
      return data.price < rule.value;
    case "rsi_above":
      return data.rsi !== undefined && data.rsi > rule.value;
    case "rsi_below":
      return data.rsi !== undefined && data.rsi < rule.value;
    case "new_signal":
      return data.hasNewSignal === true;
    default:
      return false;
  }
}

function formatCondition(condition: AlertCondition, value: number): string {
  switch (condition) {
    case "price_above":
      return `Price > ${value}`;
    case "price_below":
      return `Price < ${value}`;
    case "rsi_above":
      return `RSI > ${value}`;
    case "rsi_below":
      return `RSI < ${value}`;
    case "new_signal":
      return "New signal detected";
  }
}

// --- Hook ---

export function useAlerts(): UseAlertsReturn {
  const [alerts, setAlerts] = useState<AlertRule[]>(loadAlerts);
  const alertsRef = useRef(alerts);

  // Keep ref in sync for use inside checkAlerts callback
  useEffect(() => {
    alertsRef.current = alerts;
  }, [alerts]);

  // Persist on every change
  useEffect(() => {
    persistAlerts(alerts);
  }, [alerts]);

  // Request notification permission on mount
  useEffect(() => {
    requestNotificationPermission();
  }, []);

  const addAlert = useCallback(
    (asset: string, condition: AlertCondition, value: number) => {
      const newRule: AlertRule = {
        id: generateId(),
        asset,
        condition,
        value,
        enabled: true,
        triggered: false,
        triggeredAt: null,
      };
      setAlerts((prev) => [newRule, ...prev]);
    },
    [],
  );

  const removeAlert = useCallback((id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const toggleAlert = useCallback((id: string) => {
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, enabled: !a.enabled } : a)),
    );
  }, []);

  const clearTriggered = useCallback(() => {
    setAlerts((prev) =>
      prev.map((a) =>
        a.triggered ? { ...a, triggered: false, triggeredAt: null } : a,
      ),
    );
  }, []);

  const checkAlerts = useCallback((currentData: MarketDataPoint[]) => {
    const dataByAsset = new Map(currentData.map((d) => [d.asset, d]));
    let hasChanges = false;

    const updated = alertsRef.current.map((rule) => {
      if (!rule.enabled || rule.triggered) return rule;

      const data = dataByAsset.get(rule.asset);
      if (!data) return rule;

      if (evaluateCondition(rule, data)) {
        hasChanges = true;

        sendBrowserNotification(
          `Alert: ${rule.asset}`,
          formatCondition(rule.condition, rule.value),
        );

        return {
          ...rule,
          triggered: true,
          triggeredAt: new Date().toISOString(),
        };
      }

      return rule;
    });

    if (hasChanges) {
      setAlerts(updated);
    }
  }, []);

  const triggeredAlerts = alerts.filter((a) => a.triggered);

  return {
    alerts,
    addAlert,
    removeAlert,
    toggleAlert,
    clearTriggered,
    checkAlerts,
    triggeredAlerts,
  };
}

export type { AlertRule, AlertCondition, MarketDataPoint };
