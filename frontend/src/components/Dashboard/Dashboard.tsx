import { useQuery } from "@tanstack/react-query";
import { Component, useCallback, useEffect, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";
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
import { CorrelationPanel } from "./CorrelationPanel";
import { FundingRatePanel } from "./FundingRatePanel";
import { Heatmap } from "./Heatmap";
import { LiquidationHeatmap } from "./LiquidationHeatmap";
import { LiveRegimePanel } from "./LiveRegimePanel";
import { OrderFlowPanel } from "./OrderFlowPanel";
import { MultiChart } from "./MultiChart";
import { IntelligencePanel } from "./IntelligencePanel";
import { TradingChat } from "./TradingChat";
import { PnLSimulator } from "./PnLSimulator";

/* ── Section Error Boundary ─────────────────────────────────────────── */

interface SectionErrorBoundaryProps {
  sectionName: string;
  children: ReactNode;
}

interface SectionErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class SectionErrorBoundary extends Component<SectionErrorBoundaryProps, SectionErrorBoundaryState> {
  constructor(props: SectionErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): SectionErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[SectionErrorBoundary] ${this.props.sectionName}:`, error, info.componentStack);
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-6 text-center" role="alert">
          <p className="mb-1 text-sm font-medium text-bearish">
            {this.props.sectionName} failed to render
          </p>
          <p className="mb-3 text-xs text-gray-400">
            {this.state.error?.message ?? "An unexpected error occurred."}
          </p>
          <button
            type="button"
            onClick={this.handleRetry}
            className="rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors hover:border-accent hover:text-white"
            aria-label={`Retry loading ${this.props.sectionName}`}
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

/* ── Dashboard ─────────────────────────────────────────────────────── */

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
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [chartAsset, setChartAsset] = useState("BTCUSDT");
  const [chartTf, setChartTf] = useState("1h");
  const [exportFormat, setExportFormat] = useState<"csv" | "json">("csv");
  const [multiChartKey, setMultiChartKey] = useState(0);

  /** Item 37 — Signal card click navigates chart to that asset/timeframe */
  const handleSignalNavigate = useCallback((asset: string, timeframe?: string) => {
    setChartAsset(asset);
    if (timeframe) setChartTf(timeframe);
    setMultiChartKey((k) => k + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  // Map display format for components that expect "BTC/USDT" style
  const assetMap: Record<string, string> = {
    BTCUSDT: "BTC/USDT", ETHUSDT: "ETH/USDT", SOLUSDT: "SOL/USDT",
    BNBUSDT: "BNB/USDT", XRPUSDT: "XRP/USDT", DOGEUSDT: "DOGE/USDT",
    ADAUSDT: "ADA/USDT", AVAXUSDT: "AVAX/USDT", DOTUSDT: "DOT/USDT",
    LINKUSDT: "LINK/USDT", MATICUSDT: "MATIC/USDT", UNIUSDT: "UNI/USDT",
    ATOMUSDT: "ATOM/USDT", LTCUSDT: "LTC/USDT", FILUSDT: "FIL/USDT",
    APTUSDT: "APT/USDT", ARBUSDT: "ARB/USDT", OPUSDT: "OP/USDT",
    SUIUSDT: "SUI/USDT", PEPEUSDT: "PEPE/USDT",
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

  const handleExportSignals = useCallback(() => {
    if (activeSignals.length === 0) return;

    const exportFields = activeSignals.map((s) => ({
      asset: s.asset,
      direction: s.direction,
      confidence: s.confidence,
      entry_price: s.entry_price,
      take_profit_1: s.take_profit_1,
      take_profit_2: s.take_profit_2,
      stop_loss: s.stop_loss,
      status: s.status,
      created_at: s.created_at,
    }));

    let blob: Blob;
    let filename: string;

    if (exportFormat === "json") {
      const jsonStr = JSON.stringify(exportFields, null, 2);
      blob = new Blob([jsonStr], { type: "application/json" });
      filename = `signals_${new Date().toISOString().slice(0, 10)}.json`;
    } else {
      const headers = ["asset", "direction", "confidence", "entry_price", "take_profit_1", "take_profit_2", "stop_loss", "status", "created_at"];
      const csvRows = [
        headers.join(","),
        ...exportFields.map((row) =>
          headers.map((h) => {
            const val = row[h as keyof typeof row];
            return typeof val === "string" && val.includes(",") ? `"${val}"` : String(val);
          }).join(",")
        ),
      ];
      blob = new Blob([csvRows.join("\n")], { type: "text/csv" });
      filename = `signals_${new Date().toISOString().slice(0, 10)}.csv`;
    }

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [activeSignals, exportFormat]);

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-white sm:text-xl">AI Trading Navigator</h1>
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
      <SectionErrorBoundary sectionName="Chart">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <div className="lg:col-span-1 xl:col-span-2">
            <MultiChart key={multiChartKey} onAssetChange={(a, t) => { setChartAsset(a); setChartTf(t); }} defaultAsset={chartAsset} defaultTimeframe={chartTf} />
          </div>
          <div className="space-y-0">
            {/* Mobile sidebar toggle */}
            <button
              type="button"
              onClick={() => setSidebarVisible(!sidebarVisible)}
              className="mb-2 min-h-[44px] w-full rounded bg-surface px-3 py-2 text-xs font-medium text-gray-400 hover:text-white lg:hidden"
              aria-label={sidebarVisible ? "Hide sidebar panel" : "Show sidebar panel"}
              aria-expanded={sidebarVisible}
            >
              {sidebarVisible ? "Hide Panel" : "Show Panel"}
            </button>
            {sidebarVisible && (
              <>
                {/* Side tab selector */}
                <div className="flex border-b border-border">
                  <button type="button" onClick={() => setSideTab("orderflow")}
                    className={`min-h-[44px] flex-1 py-2 text-xs font-medium ${sideTab === "orderflow" ? "border-b-2 border-accent text-white" : "text-gray-400 hover:text-gray-200"}`}
                    aria-label="Order Flow tab">
                    Order Flow
                  </button>
                  <button type="button" onClick={() => setSideTab("chat")}
                    className={`min-h-[44px] flex-1 py-2 text-xs font-medium ${sideTab === "chat" ? "border-b-2 border-accent text-white" : "text-gray-400 hover:text-gray-200"}`}
                    aria-label="AI Chat tab">
                    AI Chat
                  </button>
                </div>
                {sideTab === "orderflow" && <OrderFlowPanel asset={chartAssetDisplay} timeframe="1m" />}
                {sideTab === "chat" && <TradingChat />}
              </>
            )}
          </div>
        </div>
      </SectionErrorBoundary>

      {/* Live Regimes */}
      <SectionErrorBoundary sectionName="Live Regimes">
        <LiveRegimePanel />
      </SectionErrorBoundary>

      {/* Market Intelligence */}
      <SectionErrorBoundary sectionName="Market Intelligence">
        <IntelligencePanel />
      </SectionErrorBoundary>

      {/* Correlation + Funding Rates */}
      <SectionErrorBoundary sectionName="Correlation & Funding Rates">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
          <CorrelationPanel />
          <FundingRatePanel />
        </div>
      </SectionErrorBoundary>

      {/* Heatmap + Liquidation Heatmap */}
      <SectionErrorBoundary sectionName="Heatmaps">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
          <Heatmap asset={chartAsset} interval={chartTf} />
          <LiquidationHeatmap asset={chartAsset} />
        </div>
      </SectionErrorBoundary>

      {/* Analysis */}
      <SectionErrorBoundary sectionName="Analysis">
        <div className="grid grid-cols-1 gap-6">
          <AnalysisPanel />
        </div>
      </SectionErrorBoundary>

      {/* Signals + Risk */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-3">
        <SectionErrorBoundary sectionName="Signal Feed">
          <div className="space-y-4 lg:col-span-2">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">Signal Feed</h2>
              {activeSignals.length > 0 && (
                <div className="flex items-center gap-2">
                  <select
                    value={exportFormat}
                    onChange={(e) => setExportFormat(e.target.value as "csv" | "json")}
                    className="min-h-[44px] rounded border border-border bg-background px-2 py-1 text-xs text-gray-400 focus:outline-none sm:min-h-0"
                    aria-label="Export format"
                  >
                    <option value="csv">CSV</option>
                    <option value="json">JSON</option>
                  </select>
                  <button
                    type="button"
                    onClick={handleExportSignals}
                    className="flex min-h-[44px] items-center gap-1.5 rounded border border-border bg-background px-3 py-1 text-xs font-medium text-gray-400 transition-colors hover:border-accent hover:text-white sm:min-h-0"
                    aria-label={`Export signals as ${exportFormat.toUpperCase()}`}
                  >
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Export
                  </button>
                </div>
              )}
            </div>
            {activeSignals.length === 0 && (
              <div className="rounded-lg border border-border bg-surface p-8 text-center text-gray-500">
                No active signals — run AI Analysis above to generate signals
              </div>
            )}
            {activeSignals.sort((a, b) => b.confidence - a.confidence).map((signal, i) => (
              <SignalCard key={signal.id} signal={signal} isNew={i === 0} onNavigate={handleSignalNavigate} />
            ))}
          </div>
        </SectionErrorBoundary>
        <SectionErrorBoundary sectionName="Risk & PnL">
          <div className="space-y-4">
            <RiskPanel
              systemStatus={systemPaused ? "PAUSED" : "ACTIVE"}
              drawdownPct={drawdownPct}
              maxDrawdownPct={settings?.max_drawdown_pct ?? 10}
              onResetKillSwitch={handleResetKillSwitch}
            />
            <PnLSimulator />
          </div>
        </SectionErrorBoundary>
      </div>
    </div>
  );
}
