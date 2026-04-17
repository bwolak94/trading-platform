import React, { useCallback, useMemo, useState } from "react";
import { useAlerts } from "../../hooks/useAlerts";
import type { AlertCondition } from "../../hooks/useAlerts";

// --- Constants ---

const ASSETS = [
  "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
  "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
  "MATICUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "FILUSDT",
  "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "PEPEUSDT",
  "EURUSD", "GBPUSD", "XAUUSD", "GBPJPY",
] as const;

const CONDITIONS: readonly { value: AlertCondition; label: string }[] = [
  { value: "price_above", label: "Price Above" },
  { value: "price_below", label: "Price Below" },
  { value: "rsi_above", label: "RSI Above" },
  { value: "rsi_below", label: "RSI Below" },
  { value: "new_signal", label: "New Signal" },
] as const;

const CONDITION_LABELS: Record<AlertCondition, string> = {
  price_above: "Price >",
  price_below: "Price <",
  rsi_above: "RSI >",
  rsi_below: "RSI <",
  new_signal: "New Signal",
};

// --- Sub-components ---

interface AlertFormProps {
  onAdd: (asset: string, condition: AlertCondition, value: number) => void;
}

const AlertForm = React.memo(function AlertForm({ onAdd }: AlertFormProps) {
  const [asset, setAsset] = useState<string>(ASSETS[0]);
  const [condition, setCondition] = useState<AlertCondition>("price_above");
  const [value, setValue] = useState<string>("");

  const isValueRequired = condition !== "new_signal";

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const numValue = isValueRequired ? parseFloat(value) : 0;
      if (isValueRequired && (isNaN(numValue) || numValue <= 0)) return;
      onAdd(asset, condition, numValue);
      setValue("");
    },
    [asset, condition, value, isValueRequired, onAdd],
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <select
          value={asset}
          onChange={(e) => setAsset(e.target.value)}
          className="rounded border border-border bg-background px-2 py-1.5 text-xs text-white focus:border-accent focus:outline-none"
          aria-label="Select asset"
        >
          {ASSETS.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <select
          value={condition}
          onChange={(e) => setCondition(e.target.value as AlertCondition)}
          className="rounded border border-border bg-background px-2 py-1.5 text-xs text-white focus:border-accent focus:outline-none"
          aria-label="Select condition"
        >
          {CONDITIONS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex gap-2">
        {isValueRequired && (
          <input
            type="number"
            step="any"
            min="0"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Value"
            className="flex-1 rounded border border-border bg-background px-2 py-1.5 text-xs text-white placeholder-gray-500 focus:border-accent focus:outline-none"
            aria-label="Alert threshold value"
          />
        )}
        <button
          type="submit"
          className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent/80"
          aria-label="Add alert rule"
        >
          Add
        </button>
      </div>
    </form>
  );
});

// --- Main Component ---

export function AlertSystem() {
  const {
    alerts,
    addAlert,
    removeAlert,
    toggleAlert,
    clearTriggered,
    triggeredAlerts,
  } = useAlerts();

  const activeAlerts = useMemo(
    () => alerts.filter((a) => !a.triggered),
    [alerts],
  );

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-500">
        Alert System
      </h3>

      {/* New alert form */}
      <AlertForm onAdd={addAlert} />

      {/* Active alerts */}
      {activeAlerts.length > 0 && (
        <div className="mt-4 space-y-2">
          <h4 className="text-xs font-medium text-gray-400">
            Active ({activeAlerts.length})
          </h4>
          <div className="max-h-48 space-y-1.5 overflow-y-auto">
            {activeAlerts.map((alert) => (
              <div
                key={alert.id}
                className="flex items-center justify-between rounded border border-border bg-background px-3 py-2"
              >
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-medium text-white">{alert.asset}</span>
                  <span className="text-gray-400">
                    {CONDITION_LABELS[alert.condition]}{" "}
                    {alert.condition !== "new_signal" && alert.value}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => toggleAlert(alert.id)}
                    className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                      alert.enabled
                        ? "bg-bullish/20 text-bullish"
                        : "bg-gray-700 text-gray-500"
                    }`}
                    aria-label={
                      alert.enabled ? "Disable alert" : "Enable alert"
                    }
                  >
                    {alert.enabled ? "ON" : "OFF"}
                  </button>
                  <button
                    type="button"
                    onClick={() => removeAlert(alert.id)}
                    className="rounded px-1.5 py-0.5 text-xs text-gray-500 transition-colors hover:bg-bearish/20 hover:text-bearish"
                    aria-label="Remove alert"
                  >
                    X
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Triggered alerts */}
      {triggeredAlerts.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-medium text-amber-400">
              Triggered ({triggeredAlerts.length})
            </h4>
            <button
              type="button"
              onClick={clearTriggered}
              className="text-xs text-gray-500 transition-colors hover:text-gray-300"
              aria-label="Clear all triggered alerts"
            >
              Clear all
            </button>
          </div>
          <div className="max-h-36 space-y-1.5 overflow-y-auto">
            {triggeredAlerts.map((alert) => (
              <div
                key={alert.id}
                className="flex items-center justify-between rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2"
              >
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-medium text-white">{alert.asset}</span>
                  <span className="text-amber-300">
                    {CONDITION_LABELS[alert.condition]}{" "}
                    {alert.condition !== "new_signal" && alert.value}
                  </span>
                </div>
                <span className="text-xs text-gray-500">
                  {alert.triggeredAt
                    ? new Date(alert.triggeredAt).toLocaleTimeString()
                    : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {alerts.length === 0 && (
        <p className="mt-3 text-center text-xs text-gray-600">
          No alerts configured. Add one above.
        </p>
      )}
    </div>
  );
}
