import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  fetchActiveSignals,
  fetchSettings,
  resetKillSwitch,
} from "../../api/client";
import { useWebSocket } from "../../hooks/useWebSocket";
import { useAppStore } from "../../store";
import type { Signal } from "../../types";
import { RiskPanel } from "../RiskPanel/RiskPanel";
import { SignalCard } from "../SignalCard/SignalCard";
import { AnalysisPanel } from "./AnalysisPanel";
import { Heatmap } from "./Heatmap";
import { LiquidationHeatmap } from "./LiquidationHeatmap";
import { LiveRegimePanel } from "./LiveRegimePanel";
import { OrderFlowPanel } from "./OrderFlowPanel";
import { PriceChart } from "./PriceChart";
import { IntelligencePanel } from "./IntelligencePanel";
import { TradingChat } from "./TradingChat";

type SideTab = "orderflow" | "chat";

export function Dashboard() {
  const { isConnected, lastMessage, subscribe } = useWebSocket();
  const {
    activeSignals, setActiveSignals, addSignal,
    settings, setSettings,
    systemPaused, setSystemPaused,
    drawdownPct, setDrawdownPct,
  } = useAppStore();

  const [sideTab, setSideTab] = useState<SideTab>("orderflow");
  const [chartAsset, setChartAsset] = useState("BTCUSDT");
  const [chartTf, setChartTf] = useState("1h");

  // Map display format for components that expect "BTC/USDT" style
  const assetMap: Record<string, string> = {
    BTCUSDT: "BTC/USDT", ETHUSDT: "ETH/USDT", SOLUSDT: "SOL/USDT",
    EURUSD: "EUR/USD", GBPUSD: "GBP/USD", XAUUSD: "XAU/USD", GBPJPY: "GBP/JPY",
  };
  const chartAssetDisplay = assetMap[chartAsset] ?? chartAsset;

  const signalsQuery = useQuery({ queryKey: ["activeSignals"], queryFn: fetchActiveSignals, refetchInterval: 30_000 });
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });

  useEffect(() => { if (signalsQuery.data) setActiveSignals(signalsQuery.data.data); }, [signalsQuery.data, setActiveSignals]);
  useEffect(() => {
    if (settingsQuery.data) {
      setSettings(settingsQuery.data);
      setSystemPaused(settingsQuery.data.system_status === "PAUSED");
    }
  }, [settingsQuery.data, setSettings, setSystemPaused]);
  useEffect(() => { if (isConnected) subscribe(["signals", "regime", "sentiment"]); }, [isConnected, subscribe]);
  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === "NEW_SIGNAL") addSignal(lastMessage.payload as unknown as Signal);
    if (lastMessage.type === "KILL_SWITCH_TRIGGERED") {
      setSystemPaused(true);
      const dd = lastMessage.payload["drawdown_pct"];
      if (typeof dd === "number") setDrawdownPct(dd);
    }
  }, [lastMessage, addSignal, setSystemPaused, setDrawdownPct]);

  const handleResetKillSwitch = async () => {
    await resetKillSwitch();
    setSystemPaused(false);
    void settingsQuery.refetch();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white">AI Trading Navigator</h1>
          <span className={`rounded px-2 py-0.5 text-xs font-bold ${systemPaused ? "bg-bearish/20 text-bearish" : "bg-bullish/20 text-bullish"}`}>
            {systemPaused ? "PAUSED" : "ACTIVE"}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className={`h-2 w-2 rounded-full ${isConnected ? "bg-bullish" : "bg-bearish"}`} />
          {isConnected ? "Connected" : "Disconnected"}
        </div>
      </div>

      {/* Chart + Side Panel */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <PriceChart onAssetChange={(a, t) => { setChartAsset(a); setChartTf(t); }} />
        </div>
        <div className="space-y-0">
          {/* Side tab selector */}
          <div className="flex border-b border-border">
            <button type="button" onClick={() => setSideTab("orderflow")}
              className={`flex-1 py-2 text-xs font-medium ${sideTab === "orderflow" ? "border-b-2 border-accent text-white" : "text-gray-400 hover:text-gray-200"}`}
              aria-label="Order Flow tab">
              Order Flow
            </button>
            <button type="button" onClick={() => setSideTab("chat")}
              className={`flex-1 py-2 text-xs font-medium ${sideTab === "chat" ? "border-b-2 border-accent text-white" : "text-gray-400 hover:text-gray-200"}`}
              aria-label="AI Chat tab">
              AI Chat
            </button>
          </div>
          {sideTab === "orderflow" && <OrderFlowPanel asset={chartAssetDisplay} timeframe="1m" />}
          {sideTab === "chat" && <TradingChat />}
        </div>
      </div>

      {/* Live Regimes */}
      <LiveRegimePanel />

      {/* Market Intelligence */}
      <IntelligencePanel />

      {/* Heatmap + Liquidation Heatmap + Analysis */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Heatmap asset={chartAsset} interval={chartTf} />
        <LiquidationHeatmap asset={chartAsset} />
      </div>

      {/* Analysis */}
      <div className="grid grid-cols-1 gap-6">
        <AnalysisPanel />
      </div>

      {/* Signals + Risk */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">Signal Feed</h2>
          {activeSignals.length === 0 && (
            <div className="rounded-lg border border-border bg-surface p-8 text-center text-gray-500">
              No active signals — run AI Analysis above to generate signals
            </div>
          )}
          {activeSignals.sort((a, b) => b.confidence - a.confidence).map((signal, i) => (
            <SignalCard key={signal.id} signal={signal} isNew={i === 0} />
          ))}
        </div>
        <div className="space-y-4">
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
