import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import {
  fetchSettings,
  updateSettings,
  resetKillSwitch,
  fetchHealth,
  fetchSystemStatus,
} from "../api/client";
import type { UserSettings } from "../types";
import { CardSkeleton } from "../components/ui/Skeleton";

const AVAILABLE_ASSETS = [
  "BTC/USDT",
  "ETH/USDT",
  "SOL/USDT",
  "BNB/USDT",
  "XRP/USDT",
  "ADA/USDT",
  "DOGE/USDT",
  "AVAX/USDT",
];

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

  const { data: systemStatus } = useQuery({
    queryKey: ["systemStatus"],
    queryFn: fetchSystemStatus,
    refetchInterval: 15_000,
  });

  // Local form state
  const [capital, setCapital] = useState(0);
  const [riskPct, setRiskPct] = useState(1.5);
  const [maxDD, setMaxDD] = useState(10);
  const [telegramId, setTelegramId] = useState("");
  const [notifications, setNotifications] = useState(true);
  const [enabledAssets, setEnabledAssets] = useState<string[]>([]);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    if (settings) {
      setCapital(settings.capital ?? 0);
      setRiskPct(settings.risk_per_trade_pct);
      setMaxDD(settings.max_drawdown_pct);
      setTelegramId(settings.telegram_chat_id ?? "");
      setNotifications(settings.notifications_enabled);
      setEnabledAssets(settings.enabled_assets);
    }
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: (data: Partial<UserSettings>) => updateSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setSaveMessage("Settings saved successfully.");
      setTimeout(() => setSaveMessage(null), 3000);
    },
    onError: () => {
      setSaveMessage("Failed to save settings.");
      setTimeout(() => setSaveMessage(null), 3000);
    },
  });

  const resetMutation = useMutation({
    mutationFn: resetKillSwitch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["systemStatus"] });
    },
  });

  const handleSave = () => {
    saveMutation.mutate({
      capital,
      risk_per_trade_pct: riskPct,
      max_drawdown_pct: maxDD,
      telegram_chat_id: telegramId || null,
      notifications_enabled: notifications,
      enabled_assets: enabledAssets,
    });
  };

  const toggleAsset = (asset: string) => {
    setEnabledAssets((prev) =>
      prev.includes(asset)
        ? prev.filter((a) => a !== asset)
        : [...prev, asset],
    );
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <div className="grid gap-6 lg:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </div>
    );
  }

  const isPaused = settings?.system_status === "PAUSED";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Settings</h1>
        {saveMessage && (
          <span
            className={`text-sm ${
              saveMessage.includes("success") ? "text-bullish" : "text-bearish"
            }`}
          >
            {saveMessage}
          </span>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Risk Management */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-gray-500">
            Risk Management
          </h2>
          <div className="space-y-4">
            <div>
              <label
                htmlFor="capital"
                className="mb-1 block text-xs text-gray-500"
              >
                Capital ($)
              </label>
              <input
                id="capital"
                type="number"
                min={0}
                step={100}
                value={capital}
                onChange={(e) => setCapital(Number(e.target.value))}
                className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-white"
                aria-label="Trading capital in dollars"
              />
            </div>
            <div>
              <label
                htmlFor="riskPct"
                className="mb-1 block text-xs text-gray-500"
              >
                Risk per Trade (%)
              </label>
              <input
                id="riskPct"
                type="number"
                min={0.1}
                max={10}
                step={0.1}
                value={riskPct}
                onChange={(e) => setRiskPct(Number(e.target.value))}
                className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-white"
                aria-label="Risk per trade percentage"
              />
            </div>
            <div>
              <label
                htmlFor="maxDD"
                className="mb-1 block text-xs text-gray-500"
              >
                Max Drawdown (%)
              </label>
              <input
                id="maxDD"
                type="number"
                min={1}
                max={50}
                step={0.5}
                value={maxDD}
                onChange={(e) => setMaxDD(Number(e.target.value))}
                className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-white"
                aria-label="Maximum drawdown percentage"
              />
            </div>
            <div className="flex items-center justify-between rounded bg-background px-3 py-2">
              <span className="text-sm text-gray-400">Kill Switch</span>
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${
                  isPaused
                    ? "bg-bearish/20 text-bearish"
                    : "bg-bullish/20 text-bullish"
                }`}
              >
                {isPaused ? "PAUSED" : "ACTIVE"}
              </span>
            </div>
            {isPaused && (
              <button
                type="button"
                onClick={() => resetMutation.mutate()}
                disabled={resetMutation.isPending}
                className="w-full rounded bg-warning px-4 py-2 text-sm font-medium text-background hover:bg-warning/80 disabled:opacity-50"
                aria-label="Reset kill switch"
              >
                {resetMutation.isPending
                  ? "Resetting..."
                  : "Reset Kill Switch"}
              </button>
            )}
          </div>
        </section>

        {/* Trading Pairs */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-gray-500">
            Trading Pairs
          </h2>
          <div className="grid grid-cols-2 gap-2">
            {AVAILABLE_ASSETS.map((asset) => (
              <label
                key={asset}
                className="flex cursor-pointer items-center gap-2 rounded bg-background px-3 py-2 text-sm text-gray-300 hover:bg-background/80"
              >
                <input
                  type="checkbox"
                  checked={enabledAssets.includes(asset)}
                  onChange={() => toggleAsset(asset)}
                  className="h-4 w-4 rounded border-border bg-background accent-bullish"
                  aria-label={`Enable ${asset}`}
                />
                <span className="font-mono">{asset}</span>
              </label>
            ))}
          </div>
        </section>

        {/* Notifications */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-gray-500">
            Notifications
          </h2>
          <div className="space-y-4">
            <div>
              <label
                htmlFor="telegramId"
                className="mb-1 block text-xs text-gray-500"
              >
                Telegram Chat ID
              </label>
              <input
                id="telegramId"
                type="text"
                value={telegramId}
                onChange={(e) => setTelegramId(e.target.value)}
                placeholder="e.g. 123456789"
                className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-white placeholder-gray-600"
                aria-label="Telegram chat ID"
              />
            </div>
            <div className="flex items-center justify-between rounded bg-background px-3 py-2">
              <span className="text-sm text-gray-400">
                Enable Notifications
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={notifications}
                aria-label="Toggle notifications"
                onClick={() => setNotifications(!notifications)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                  notifications ? "bg-bullish" : "bg-gray-600"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                    notifications ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>
          </div>
        </section>

        {/* System Status */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-gray-500">
            System
          </h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded bg-background px-3 py-2">
              <span className="text-sm text-gray-400">API Health</span>
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${
                  health?.status === "ok"
                    ? "bg-bullish/20 text-bullish"
                    : "bg-bearish/20 text-bearish"
                }`}
              >
                {health?.status === "ok" ? "Healthy" : "Unavailable"}
              </span>
            </div>
            <div className="flex items-center justify-between rounded bg-background px-3 py-2">
              <span className="text-sm text-gray-400">System Status</span>
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${
                  systemStatus?.system_status === "ACTIVE"
                    ? "bg-bullish/20 text-bullish"
                    : "bg-warning/20 text-warning"
                }`}
              >
                {systemStatus?.system_status ?? "Unknown"}
              </span>
            </div>
            <div className="flex items-center justify-between rounded bg-background px-3 py-2">
              <span className="text-sm text-gray-400">WebSocket Clients</span>
              <span className="font-mono text-sm text-white">
                {systemStatus?.websocket_clients ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between rounded bg-background px-3 py-2">
              <span className="text-sm text-gray-400">Current Drawdown</span>
              <span
                className={`font-mono text-sm ${
                  (systemStatus?.drawdown_pct ?? 0) > 5
                    ? "text-bearish"
                    : "text-white"
                }`}
              >
                {systemStatus?.drawdown_pct?.toFixed(2) ?? "0.00"}%
              </span>
            </div>
          </div>
        </section>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="rounded bg-bullish px-6 py-2 text-sm font-medium text-background hover:bg-bullish/80 disabled:opacity-50"
          aria-label="Save settings"
        >
          {saveMutation.isPending ? "Saving..." : "Save Settings"}
        </button>
      </div>
    </div>
  );
}
