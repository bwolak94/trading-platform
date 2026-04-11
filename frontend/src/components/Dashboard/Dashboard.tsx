import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  fetchActiveSignals,
  fetchRegimes,
  fetchSentiment,
  fetchSettings,
  resetKillSwitch,
} from "../../api/client";
import { useWebSocket } from "../../hooks/useWebSocket";
import { useAppStore } from "../../store";
import type { Signal } from "../../types";
import { RegimePanel } from "../RegimeIndicator/RegimeIndicator";
import { RiskPanel } from "../RiskPanel/RiskPanel";
import { SignalCard } from "../SignalCard/SignalCard";
import { SentimentBar } from "./SentimentBar";

export function Dashboard() {
  const { isConnected, lastMessage, subscribe } = useWebSocket();
  const {
    activeSignals,
    setActiveSignals,
    addSignal,
    regimes,
    setRegimes,
    settings,
    setSettings,
    systemPaused,
    setSystemPaused,
    drawdownPct,
    setDrawdownPct,
  } = useAppStore();

  // Fetch initial data
  const signalsQuery = useQuery({
    queryKey: ["activeSignals"],
    queryFn: fetchActiveSignals,
    refetchInterval: 30_000,
  });

  const regimesQuery = useQuery({
    queryKey: ["regimes"],
    queryFn: fetchRegimes,
    refetchInterval: 60_000,
  });

  const sentimentQuery = useQuery({
    queryKey: ["sentiment"],
    queryFn: fetchSentiment,
    refetchInterval: 60_000,
  });

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });

  // Sync query data to store
  useEffect(() => {
    if (signalsQuery.data) setActiveSignals(signalsQuery.data.data);
  }, [signalsQuery.data, setActiveSignals]);

  useEffect(() => {
    if (regimesQuery.data) setRegimes(regimesQuery.data);
  }, [regimesQuery.data, setRegimes]);

  useEffect(() => {
    if (settingsQuery.data) {
      setSettings(settingsQuery.data);
      setSystemPaused(settingsQuery.data.system_status === "PAUSED");
    }
  }, [settingsQuery.data, setSettings, setSystemPaused]);

  // Subscribe to WebSocket channels
  useEffect(() => {
    if (isConnected) {
      subscribe(["signals", "regime", "sentiment"]);
    }
  }, [isConnected, subscribe]);

  // Handle incoming WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;

    if (lastMessage.type === "NEW_SIGNAL") {
      addSignal(lastMessage.payload as unknown as Signal);
    }
    if (lastMessage.type === "KILL_SWITCH_TRIGGERED") {
      setSystemPaused(true);
      const dd = lastMessage.payload["drawdown_pct"];
      if (typeof dd === "number") setDrawdownPct(dd);
    }
    if (lastMessage.type === "REGIME_CHANGE" && regimesQuery.refetch) {
      void regimesQuery.refetch();
    }
  }, [lastMessage, addSignal, setSystemPaused, setDrawdownPct, regimesQuery]);

  const handleResetKillSwitch = async () => {
    await resetKillSwitch();
    setSystemPaused(false);
    void settingsQuery.refetch();
  };

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white">AI Trading Navigator</h1>
          <span
            className={`rounded px-2 py-0.5 text-xs font-bold ${
              systemPaused
                ? "bg-bearish/20 text-bearish"
                : "bg-bullish/20 text-bullish"
            }`}
          >
            {systemPaused ? "PAUSED" : "ACTIVE"}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span
            className={`h-2 w-2 rounded-full ${isConnected ? "bg-bullish" : "bg-bearish"}`}
          />
          {isConnected ? "Connected" : "Disconnected"}
        </div>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Signal Feed — spans 2 columns */}
        <div className="space-y-4 lg:col-span-2">
          <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">
            Signal Feed
          </h2>
          {activeSignals.length === 0 && (
            <div className="rounded-lg border border-border bg-surface p-8 text-center text-gray-500">
              No active signals
            </div>
          )}
          {activeSignals
            .sort((a, b) => b.confidence - a.confidence)
            .map((signal, i) => (
              <SignalCard key={signal.id} signal={signal} isNew={i === 0} />
            ))}
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          <RegimePanel regimes={regimes} />
          <SentimentBar sentiments={sentimentQuery.data ?? []} />
          <RiskPanel
            systemStatus={systemPaused ? "PAUSED" : "ACTIVE"}
            drawdownPct={drawdownPct}
            maxDrawdownPct={settings?.max_drawdown_pct ?? 10}
            onResetKillSwitch={handleResetKillSwitch}
          />
        </div>
      </div>
    </div>
  );
}
