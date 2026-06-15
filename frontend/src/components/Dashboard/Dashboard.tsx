import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import {
  fetchActiveSignals,
  fetchSettings,
  resetKillSwitch,
  startSimulation,
  stopSimulation,
  type SimulatedPosition,
} from "../../api/client";
import { useWebSocket } from "../../hooks/useWebSocket";
import { useAppStore } from "../../store";
import type { Signal } from "../../types";
import { RiskPanel } from "../RiskPanel/RiskPanel";
import { SignalCard } from "../SignalCard/SignalCard";
import { AnalysisPanel } from "./AnalysisPanel";
import { BotPerformancePanel } from "./BotPerformancePanel";
import { CorrelationPanel } from "./CorrelationPanel";
import { PositionDetailDrawer } from "./PositionDetailDrawer";
import { FundingRatePanel } from "./FundingRatePanel";
import { Heatmap } from "./Heatmap";
import { LiquidationHeatmap } from "./LiquidationHeatmap";
import { LiveRegimePanel } from "./LiveRegimePanel";
import { NotificationHistoryPanel } from "./NotificationHistoryPanel";
import { SignalHistoryPanel } from "./SignalHistoryPanel";
import { OrderFlowPanel } from "./OrderFlowPanel";
import { MultiChart } from "./MultiChart";
import { IntelligencePanel } from "./IntelligencePanel";
import { SimulationPanel } from "./SimulationPanel";
import { TradingChat } from "./TradingChat";
import { PnLSimulator } from "./PnLSimulator";
import { CommandPalette } from "../ui/CommandPalette";
import { useHotkeys } from "../hooks/useHotkeys";
import { ShortcutsHelp } from "../ui/ShortcutsHelp";
import { EquityCurvePanel } from "./EquityCurvePanel";
// MonteCarloPanel is available in the Advanced tab via dynamic import if needed
import { MarketOverviewPanel } from "./MarketOverviewPanel";
import { MomentumRankPanel } from "./MomentumRankPanel";
import { StrategyHeatmapPanel } from "./StrategyHeatmapPanel";
import { AttributionPanel } from "./AttributionPanel";
import { TradeDurationPanel } from "./TradeDurationPanel";
import { EntryTimingHeatmapPanel } from "./EntryTimingHeatmapPanel";
import { FundingHeatmapPanel } from "./FundingHeatmapPanel";
import { ExposureHeatmapPanel } from "./ExposureHeatmapPanel";
import { LiveReadinessPanel } from "./LiveReadinessPanel";
import { MacroPanel } from "./MacroPanel";
import { MarketSentimentPanel } from "./MarketSentimentPanel";
import { SectorMomentumPanel } from "./SectorMomentumPanel";
import { SessionClock } from "../ui/SessionClock";
// SettingsPanel rendered in settings modal conditionally
import { OpenInterestPanel } from "./OpenInterestPanel";
import { useTheme } from "../hooks/useTheme";
import { usePanelOrder } from "../hooks/usePanelOrder";
// PanelId type used in drag-drop panel ordering hooks
import { MTFSignalMatrix } from "./MTFSignalMatrix";
import { BenchmarkPanel } from "./BenchmarkPanel";
import { StressTestScenariosPanel } from "./StressTestScenariosPanel";
import { SignalConfidenceTrend } from "./SignalConfidenceTrend";
import { SoundSettings } from "./SoundSettings";
import { EarningsCalendarPanel } from "./EarningsCalendarPanel";
import { NewsSentimentVelocity } from "./NewsSentimentVelocity";
import { FundingArbitragePanel } from "./FundingArbitragePanel";
import { MarketMicrostructureScore } from "./MarketMicrostructureScore";
import { RegimeTransitionForecast } from "./RegimeTransitionForecast";
import { DrawdownBudgetWidget } from "./DrawdownBudgetWidget";
import { SessionReplayWidget } from "./SessionReplayWidget";
import { AlertFormulaBuilder } from "./AlertFormulaBuilder";
import { LayoutPresets, useLayoutPreset } from "../ui/LayoutPresets";
import WyckoffPhasePanel from "./WyckoffPhasePanel";
import SupplyDemandZonesPanel from "./SupplyDemandZonesPanel";
import FibConfluencePanel from "./FibConfluencePanel";
import OptionsFlowPanel from "./OptionsFlowPanel";
import MarketProfilePanel from "./MarketProfilePanel";
import IntermarketPanel from "./IntermarketPanel";
import SpreadQualityWidget from "./SpreadQualityWidget";
import RecoveryProtocolWidget from "./RecoveryProtocolWidget";
import DeltaNeutralCalculator from "./DeltaNeutralCalculator";
import ConfidencePercentileWidget from "./ConfidencePercentileWidget";
import SeasonalityPanel from "./SeasonalityPanel";
import CrossExchangeMonitor from "./CrossExchangeMonitor";
import TradeJournalPanel from "./TradeJournalPanel";
import PortfolioRiskDashboard from "./PortfolioRiskDashboard";
import MarketModeSelector from "./MarketModeSelector";
import ConvictionScoreWidget from "./ConvictionScoreWidget";
import SignalRiskPanel from "./SignalRiskPanel";
import StopHuntPanel from "./StopHuntPanel";
import CarryOptimizerPanel from "./CarryOptimizerPanel";
import StreakCircuitBreakerWidget from "./StreakCircuitBreakerWidget";
import CVDDivergenceWidget from "./CVDDivergenceWidget";
import SmartMoneyFlowWidget from "./SmartMoneyFlowWidget";
import OvernightGapWidget from "./OvernightGapWidget";
import AnnotatedBenchmarkPanel from "./AnnotatedBenchmarkPanel";
import PatternPerformancePanel from "./PatternPerformancePanel";
import { AIBotTab } from "./AIBotTab";
import { KellyCriterionPanel } from "./KellyCriterionPanel";
import { PortfolioPnLHeatmap } from "./PortfolioPnLHeatmap";
import { LiquidationCascadePanel } from "./LiquidationCascadePanel";
import { WatchlistPanel } from "./WatchlistPanel";
import { MAETrackerPanel } from "./MAETrackerPanel";
import { SentimentDivergencePanel } from "./SentimentDivergencePanel";
import { NewsRiskGuard } from "./NewsRiskGuard";
import { RiskPositionSizerWidget } from "./RiskPositionSizerWidget";
import { DrawdownWaterfallChart } from "./DrawdownWaterfallChart";
import { FundingRateHistoryPanel } from "./FundingRateHistoryPanel";
import { SessionPnLPanel } from "./SessionPnLPanel";
import { MultiExchangePanel } from "./MultiExchangePanel";
import { OIMomentumPanel } from "./OIMomentumPanel";
import { DarkPoolPanel } from "./DarkPoolPanel";
import { PnLAttributionHeatmap } from "./PnLAttributionHeatmap";
import { CorrelationShockPanel } from "./CorrelationShockPanel";
import { PositionJournalPanel } from "./PositionJournalPanel";
import { PaperLeaderboardPanel } from "./PaperLeaderboardPanel";
import { SpreadTrackerPanel } from "./SpreadTrackerPanel";
import { VolatilitySurfacePanel } from "./VolatilitySurfacePanel";
import { MorningBriefPanel } from "./MorningBriefPanel";
import { NewsEventBacktesterPanel } from "./NewsEventBacktesterPanel";
// A5: Heavy panels are lazy-loaded to reduce initial JS parse time.
// They are code-split into separate chunks and only downloaded on first render.
const MultiAssetCorrelationMatrix = lazy(() =>
  import("./MultiAssetCorrelationMatrix").then((m) => ({ default: m.MultiAssetCorrelationMatrix })),
);
const LiquidityDepthHeatmap = lazy(() =>
  import("./LiquidityDepthHeatmap").then((m) => ({ default: m.LiquidityDepthHeatmap })),
);
const StrategyABBacktester = lazy(() =>
  import("./StrategyABBacktester").then((m) => ({ default: m.StrategyABBacktester })),
);

// Additional heavy panels — code-split to reduce initial bundle parse time
const RegimeTransitionTimeline = lazy(() =>
  import("./RegimeTransitionTimeline").then((m) => ({ default: m.RegimeTransitionTimeline })),
);
const SmartStopLossOptimizer = lazy(() =>
  import("./SmartStopLossOptimizer").then((m) => ({ default: m.SmartStopLossOptimizer })),
);
const TradeSetupScreener = lazy(() =>
  import("./TradeSetupScreener").then((m) => ({ default: m.TradeSetupScreener })),
);
const MacroCountdownWidget = lazy(() =>
  import("./MacroCountdownWidget").then((m) => ({ default: m.MacroCountdownWidget })),
);
const RiskOfRuinMeter = lazy(() =>
  import("./RiskOfRuinMeter").then((m) => ({ default: m.RiskOfRuinMeter })),
);
const SignalReplayMode = lazy(() =>
  import("./SignalReplayMode").then((m) => ({ default: m.SignalReplayMode })),
);
import { useNotificationBadge } from "../../hooks/useNotificationBadge";

/* ── Section wrapper uses the shared ErrorBoundary from ui/ ─────────── */

function SectionErrorBoundary({
  sectionName,
  children,
}: {
  sectionName: string;
  children: ReactNode;
}) {
  return (
    <ErrorBoundary componentName={sectionName}>
      {children}
    </ErrorBoundary>
  );
}

/* ── Dashboard ─────────────────────────────────────────────────────── */

type SideTab = "orderflow" | "chat";
type ExtendedMainTab = "dashboard" | "positioning" | "bot" | "advanced";

const MAIN_TABS: ExtendedMainTab[] = ["dashboard", "positioning", "bot", "advanced"];

export function Dashboard() {
  const { isConnected, lastMessage, subscribe } = useWebSocket();
  const {
    activeSignals, setActiveSignals, addSignal,
    settings, setSettings,
    systemPaused, setSystemPaused,
    drawdownPct, setDrawdownPct,
    activeMainTab: storeMainTab, setActiveMainTab: setStoreMainTab,
  } = useAppStore();

  // Extended tab state that adds "advanced" on top of the store's two tabs
  const [extendedTab, setExtendedTab] = useState<ExtendedMainTab>(storeMainTab);

  const activeMainTab = extendedTab;
  const setActiveMainTab = useCallback((tab: ExtendedMainTab) => {
    setExtendedTab(tab);
    if (tab === "dashboard" || tab === "positioning") {
      setStoreMainTab(tab);
    }
  }, [setStoreMainTab]);

  // Theme management (applies data-theme attribute to document root)
  useTheme();

  const { resetLayout } = usePanelOrder();
  const [_showSettings, setShowSettings] = useState(false);

  const [sideTab, setSideTab] = useState<SideTab>("orderflow");
  const { activePreset, applyPreset } = useLayoutPreset();
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [chartAsset, setChartAsset] = useState("BTCUSDT");
  const [chartTf, setChartTf] = useState("1h");
  const [exportFormat, setExportFormat] = useState<"csv" | "json">("csv");
  const [multiChartKey, setMultiChartKey] = useState(0);
  const [focusedPosition, setFocusedPosition] = useState<SimulatedPosition | null>(null);

  /** Command palette — navigate chart to a symbol */
  const handleCommandPaletteSymbol = useCallback((symbol: string) => {
    setChartAsset(symbol);
    setMultiChartKey((k) => k + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  /** Command palette — start simulation bot */
  const handleCommandPaletteStartBot = useCallback(() => {
    void startSimulation();
  }, []);

  /** Command palette — stop simulation bot */
  const handleCommandPaletteStopBot = useCallback(() => {
    void stopSimulation();
  }, []);

  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);

  /** Signal card click navigates chart to that asset/timeframe */
  const handleSignalNavigate = useCallback((asset: string, timeframe?: string) => {
    setChartAsset(asset);
    if (timeframe) setChartTf(timeframe);
    setMultiChartKey((k) => k + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  /** Simulation position click — open drawer and navigate chart */
  const handlePositionClick = useCallback((pos: SimulatedPosition) => {
    setFocusedPosition(pos);
  }, []);

  /** Navigate chart from drawer "View on Chart" button */
  const handleDrawerNavigate = useCallback((symbol: string) => {
    setChartAsset(symbol);
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

  // Global asset filter — filters signal list and propagates to panels that support it
  const [globalAssetFilter, setGlobalAssetFilter] = useState("");

  const signalsQuery = useQuery({
    queryKey: ["activeSignals"],
    queryFn: fetchActiveSignals,
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
    placeholderData: (prev) => prev,
  });

  // Notification badge: count of new (< 5 min old) active signals
  const newSignalCount = activeSignals.filter((s) => {
    const age = Date.now() - new Date(s.created_at).getTime();
    return age < 5 * 60 * 1000 && s.status === "ACTIVE";
  }).length;
  useNotificationBadge(newSignalCount);

  // Deduplication: flag signals sharing the same asset+direction within 15 min
  const dedupKeys = new Set<string>();
  const signalDupMap = new Map<string, boolean>();
  const sortedByTime = [...activeSignals].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
  for (const sig of sortedByTime) {
    const ageMin = (Date.now() - new Date(sig.created_at).getTime()) / 60000;
    const key = `${sig.asset}:${sig.direction}`;
    if (ageMin < 15 && dedupKeys.has(key)) {
      signalDupMap.set(sig.id, true);
    } else {
      dedupKeys.add(key);
    }
  }

  // Filtered signals based on global asset filter
  const filteredSignals = globalAssetFilter
    ? activeSignals.filter((s) => s.asset.toLowerCase().includes(globalAssetFilter.toLowerCase()))
    : activeSignals;


  useHotkeys({
    onTimeframeChange: useCallback((tf: string) => { setChartTf(tf); setMultiChartKey((k) => k + 1); }, []),
    onRefresh: useCallback(() => { void signalsQuery.refetch(); }, [signalsQuery]),
    onNextTab: useCallback(() => {
      const next = MAIN_TABS[(MAIN_TABS.indexOf(activeMainTab) + 1) % MAIN_TABS.length];
      if (next) setActiveMainTab(next);
    }, [activeMainTab, setActiveMainTab]),
    onPrevTab: useCallback(() => {
      const prev = MAIN_TABS[(MAIN_TABS.indexOf(activeMainTab) + MAIN_TABS.length - 1) % MAIN_TABS.length];
      if (prev) setActiveMainTab(prev);
    }, [activeMainTab, setActiveMainTab]),
  });

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
      const dd = lastMessage.payload.drawdown_pct;
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
        <SessionClock />
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={resetLayout}
            className="rounded border border-border/50 px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Reset dashboard panel layout to default"
            title="Reset layout"
          >
            Reset Layout
          </button>
          <button
            type="button"
            onClick={() => { setShowShortcutsHelp(true); }}
            className="rounded border border-border/50 px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Show keyboard shortcuts"
            title="Keyboard shortcuts (?)"
          >
            ?
          </button>
          <button
            type="button"
            onClick={() => { setShowSettings(true); }}
            className="rounded border border-border/50 p-1.5 text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Open settings"
            title="Settings"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </div>

      {/* G2: ARIA live region for kill-switch / regime-change alerts — screen readers
           announce these immediately when they appear */}
      <div aria-live="assertive" aria-atomic="true" className="sr-only">
        {systemPaused && "Alert: Kill switch active. Trading is paused due to drawdown limit."}
      </div>

      {/* Macro Countdown — always visible strip */}
      <div className="border-b border-border px-4 py-2">
        <MacroCountdownWidget />
      </div>

      {/* Market Mode Selector + Global Asset Filter */}
      <div className="border-b border-border px-4 py-3 flex items-center gap-3">
        <div className="flex-1">
          <MarketModeSelector />
        </div>
        <div className="flex items-center gap-1.5">
          <label htmlFor="global-asset-filter" className="text-[10px] text-gray-500 shrink-0">
            Filter asset:
          </label>
          <input
            id="global-asset-filter"
            type="text"
            value={globalAssetFilter}
            onChange={(e) => { setGlobalAssetFilter(e.target.value); }}
            placeholder="BTC, ETH…"
            className="w-24 rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Filter signals by asset"
          />
          {globalAssetFilter && (
            <button
              type="button"
              onClick={() => { setGlobalAssetFilter(""); }}
              className="text-gray-500 hover:text-gray-300 text-xs"
              aria-label="Clear asset filter"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Main tab navigation */}
      <div className="flex overflow-x-auto border-b border-border" role="tablist" aria-label="Main navigation tabs">
        {(["dashboard", "positioning", "bot", "advanced"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeMainTab === tab}
            onClick={() => { setActiveMainTab(tab); }}
            className={`min-h-[44px] shrink-0 px-5 py-2 text-sm font-medium transition-colors ${
              activeMainTab === tab
                ? "border-b-2 border-accent text-white"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab === "dashboard" ? "Dashboard"
              : tab === "positioning" ? "Open Interest"
              : tab === "bot" ? (
                <span className="flex items-center gap-1.5">
                  Bot
                  <span className="rounded-full bg-bullish/25 px-1.5 py-0.5 text-[9px] font-bold text-bullish">LIVE</span>
                </span>
              )
              : "Advanced"}
          </button>
        ))}
      </div>

      {/* Layout Presets toolbar — visible on dashboard tab */}
      {activeMainTab === "dashboard" && (
        <div className="border-b border-border px-4 py-2">
          <LayoutPresets onApplyPreset={applyPreset} activePreset={activePreset} />
        </div>
      )}

      {/* Bot tab */}
      {activeMainTab === "bot" && (
        <SectionErrorBoundary sectionName="AI Bot">
          <AIBotTab />
        </SectionErrorBoundary>
      )}

      {/* Positioning tab */}
      {activeMainTab === "positioning" && (
        <SectionErrorBoundary sectionName="Positioning">
          <OpenInterestPanel defaultSymbol={chartAsset} />
        </SectionErrorBoundary>
      )}

      {/* Advanced tab */}
      {activeMainTab === "advanced" && (
        <div className="space-y-4 sm:space-y-6">

          {/* MTF Signal Matrix */}
          <SectionErrorBoundary sectionName="MTF Signal Matrix">
            <MTFSignalMatrix onAssetSelect={handleSignalNavigate} />
          </SectionErrorBoundary>

          {/* Regime Transition Forecast */}
          <SectionErrorBoundary sectionName="Regime Transition Forecast">
            <RegimeTransitionForecast />
          </SectionErrorBoundary>

          {/* Market Microstructure + Drawdown Budget */}
          <SectionErrorBoundary sectionName="Microstructure & Budget">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <MarketMicrostructureScore />
              <DrawdownBudgetWidget />
            </div>
          </SectionErrorBoundary>

          {/* Benchmark + Stress Test */}
          <SectionErrorBoundary sectionName="Benchmark & Stress Test">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <BenchmarkPanel />
              <StressTestScenariosPanel />
            </div>
          </SectionErrorBoundary>

          {/* Signal Confidence Trend */}
          <SectionErrorBoundary sectionName="Signal Confidence Trend">
            <SignalConfidenceTrend />
          </SectionErrorBoundary>

          {/* Funding Arbitrage + Earnings Calendar */}
          <SectionErrorBoundary sectionName="Funding Arbitrage & Calendar">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <FundingArbitragePanel onViewChart={handleSignalNavigate} />
              <EarningsCalendarPanel />
            </div>
          </SectionErrorBoundary>

          {/* News Sentiment Velocity */}
          <SectionErrorBoundary sectionName="News Sentiment">
            <NewsSentimentVelocity />
          </SectionErrorBoundary>

          {/* Alert Formula Builder + Session Replay */}
          <SectionErrorBoundary sectionName="Alert Builder & Session Replay">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <AlertFormulaBuilder />
              <div className="space-y-4">
                <SessionReplayWidget />
                <SoundSettings />
              </div>
            </div>
          </SectionErrorBoundary>

          {/* ── NEW FEATURE PANELS ─────────────────────────────────── */}

          {/* Trade Journal (AI insights from trade history) */}
          <SectionErrorBoundary sectionName="Trade Journal">
            <TradeJournalPanel />
          </SectionErrorBoundary>

          {/* Wyckoff + Supply/Demand Zones */}
          <SectionErrorBoundary sectionName="Wyckoff & Supply/Demand">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <WyckoffPhasePanel />
              <SupplyDemandZonesPanel />
            </div>
          </SectionErrorBoundary>

          {/* Fibonacci Confluence + Market Profile */}
          <SectionErrorBoundary sectionName="Fibonacci & Market Profile">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <FibConfluencePanel />
              <MarketProfilePanel />
            </div>
          </SectionErrorBoundary>

          {/* Options Flow + Intermarket Analysis */}
          <SectionErrorBoundary sectionName="Options Flow & Intermarket">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <OptionsFlowPanel />
              <IntermarketPanel />
            </div>
          </SectionErrorBoundary>

          {/* Seasonality + Confidence Percentile */}
          <SectionErrorBoundary sectionName="Seasonality & Signal Rank">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <SeasonalityPanel />
              <ConfidencePercentileWidget />
            </div>
          </SectionErrorBoundary>

          {/* Cross-Exchange Monitor + Spread Quality */}
          <SectionErrorBoundary sectionName="Cross-Exchange & Entry Quality">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <CrossExchangeMonitor />
              <SpreadQualityWidget />
            </div>
          </SectionErrorBoundary>

          {/* Recovery Protocol + Delta-Neutral Calculator */}
          <SectionErrorBoundary sectionName="Recovery Protocol & Delta-Neutral">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <RecoveryProtocolWidget />
              <DeltaNeutralCalculator />
            </div>
          </SectionErrorBoundary>

          {/* Portfolio Risk Dashboard */}
          <SectionErrorBoundary sectionName="Portfolio Risk">
            <PortfolioRiskDashboard />
          </SectionErrorBoundary>

          {/* Conviction + Signal Risk */}
          <SectionErrorBoundary sectionName="Signal Quality Gate">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <ConvictionScoreWidget />
              <SignalRiskPanel />
            </div>
          </SectionErrorBoundary>

          {/* Stop Hunt + CVD Divergence */}
          <SectionErrorBoundary sectionName="Stop Hunt & CVD">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <StopHuntPanel />
              <CVDDivergenceWidget />
            </div>
          </SectionErrorBoundary>

          {/* Carry Optimizer + Smart Money Flow */}
          <SectionErrorBoundary sectionName="Carry & Smart Money">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <CarryOptimizerPanel />
              <SmartMoneyFlowWidget />
            </div>
          </SectionErrorBoundary>

          {/* Overnight Gap + Pattern Performance */}
          <SectionErrorBoundary sectionName="Gap Risk & Pattern Performance">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <OvernightGapWidget />
              <PatternPerformancePanel />
            </div>
          </SectionErrorBoundary>

          {/* Annotated Benchmark */}
          <SectionErrorBoundary sectionName="Annotated Benchmark">
            <AnnotatedBenchmarkPanel />
          </SectionErrorBoundary>

          {/* News Risk Guard — macro event proximity banner */}
          <SectionErrorBoundary sectionName="News Risk Guard">
            <NewsRiskGuard />
          </SectionErrorBoundary>

          {/* Sentiment Divergence + Liquidation Cascade */}
          <SectionErrorBoundary sectionName="Sentiment & Cascade Risk">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <SentimentDivergencePanel />
              <LiquidationCascadePanel />
            </div>
          </SectionErrorBoundary>

          {/* Kelly Criterion + MAE Tracker */}
          <SectionErrorBoundary sectionName="Kelly & MAE">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <KellyCriterionPanel />
              <MAETrackerPanel />
            </div>
          </SectionErrorBoundary>

          {/* Portfolio P&L Heatmap */}
          <SectionErrorBoundary sectionName="P&L Heatmap">
            <PortfolioPnLHeatmap />
          </SectionErrorBoundary>

          {/* Watchlist & Price Alerts */}
          <SectionErrorBoundary sectionName="Watchlist">
            <WatchlistPanel />
          </SectionErrorBoundary>

          {/* Risk Position Sizer + Drawdown Waterfall */}
          <SectionErrorBoundary sectionName="Position Sizer & Drawdown">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <RiskPositionSizerWidget />
              <DrawdownWaterfallChart />
            </div>
          </SectionErrorBoundary>

          {/* Funding Rate History + OI Momentum */}
          <SectionErrorBoundary sectionName="Funding & OI Momentum">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <FundingRateHistoryPanel />
              <OIMomentumPanel />
            </div>
          </SectionErrorBoundary>

          {/* Session P&L + Dark Pool */}
          <SectionErrorBoundary sectionName="Session P&L & Dark Pool">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <SessionPnLPanel />
              <DarkPoolPanel />
            </div>
          </SectionErrorBoundary>

          {/* Multi-Exchange Prices + Volatility Surface */}
          <SectionErrorBoundary sectionName="Multi-Exchange & Vol Surface">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <MultiExchangePanel />
              <VolatilitySurfacePanel />
            </div>
          </SectionErrorBoundary>

          {/* Correlation Shock + Spread Tracker */}
          <SectionErrorBoundary sectionName="Correlation Shock & Spreads">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <CorrelationShockPanel />
              <SpreadTrackerPanel />
            </div>
          </SectionErrorBoundary>

          {/* P&L Attribution Heatmap */}
          <SectionErrorBoundary sectionName="P&L Attribution">
            <PnLAttributionHeatmap />
          </SectionErrorBoundary>

          {/* Paper Leaderboard + Position Journal */}
          <SectionErrorBoundary sectionName="Leaderboard & Journal">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <PaperLeaderboardPanel />
              <PositionJournalPanel />
            </div>
          </SectionErrorBoundary>

          {/* News Event Backtester */}
          <SectionErrorBoundary sectionName="News Event Backtester">
            <NewsEventBacktesterPanel />
          </SectionErrorBoundary>

          {/* ── NEW FEATURES FROM IMPROVEMENTS BATCH ────────────── */}

          {/* Multi-Asset Correlation Matrix — A5: lazy-loaded */}
          <SectionErrorBoundary sectionName="Correlation Matrix">
            <Suspense fallback={<div className="h-32 animate-pulse rounded-lg bg-surface" />}>
              <MultiAssetCorrelationMatrix />
            </Suspense>
          </SectionErrorBoundary>

          {/* Regime Transition Timeline */}
          <SectionErrorBoundary sectionName="Regime Timeline">
            <RegimeTransitionTimeline />
          </SectionErrorBoundary>

          {/* Signal Replay Mode */}
          <SectionErrorBoundary sectionName="Signal Replay">
            <SignalReplayMode />
          </SectionErrorBoundary>

          {/* Smart Stop Loss Optimizer + Strategy A/B Backtester — A5: heavy panels lazy-loaded */}
          <SectionErrorBoundary sectionName="Optimization Suite">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <SmartStopLossOptimizer />
              <Suspense fallback={<div className="h-64 animate-pulse rounded-lg bg-surface" />}>
                <StrategyABBacktester />
              </Suspense>
            </div>
          </SectionErrorBoundary>

          {/* Trade Setup Screener */}
          <SectionErrorBoundary sectionName="Trade Screener">
            <TradeSetupScreener />
          </SectionErrorBoundary>

          {/* Risk of Ruin Meter + Liquidity Depth Heatmap — A5: heatmap lazy-loaded */}
          <SectionErrorBoundary sectionName="Risk & Liquidity">
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              <RiskOfRuinMeter currentDrawdownPct={drawdownPct} />
              <Suspense fallback={<div className="h-64 animate-pulse rounded-lg bg-surface" />}>
                <LiquidityDepthHeatmap />
              </Suspense>
            </div>
          </SectionErrorBoundary>

        </div>
      )}

      {/* Dashboard tab content */}
      {activeMainTab === "dashboard" && <>

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
              onClick={() => { setSidebarVisible(!sidebarVisible); }}
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
                  <button type="button" onClick={() => { setSideTab("orderflow"); }}
                    className={`min-h-[44px] flex-1 py-2 text-xs font-medium ${sideTab === "orderflow" ? "border-b-2 border-accent text-white" : "text-gray-400 hover:text-gray-200"}`}
                    aria-label="Order Flow tab">
                    Order Flow
                  </button>
                  <button type="button" onClick={() => { setSideTab("chat"); }}
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

      {/* Morning Brief */}
      <SectionErrorBoundary sectionName="Morning Brief">
        <MorningBriefPanel />
      </SectionErrorBoundary>

      {/* Live Regimes + Regime Transition Forecast */}
      <SectionErrorBoundary sectionName="Live Regimes">
        <LiveRegimePanel />
      </SectionErrorBoundary>
      <SectionErrorBoundary sectionName="Regime Transition Forecast">
        <RegimeTransitionForecast />
      </SectionErrorBoundary>

      {/* MTF Signal Matrix */}
      <SectionErrorBoundary sectionName="MTF Signal Matrix">
        <MTFSignalMatrix onAssetSelect={handleSignalNavigate} />
      </SectionErrorBoundary>

      {/* Market Overview + Microstructure Score */}
      <SectionErrorBoundary sectionName="Market Overview">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <MarketOverviewPanel />
          </div>
          <div className="space-y-4">
            <MomentumRankPanel />
            <MarketMicrostructureScore />
          </div>
        </div>
      </SectionErrorBoundary>

      {/* Macro Overlay + Sector Momentum */}
      <SectionErrorBoundary sectionName="Macro & Sector Momentum">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
          <MacroPanel />
          <SectorMomentumPanel />
        </div>
      </SectionErrorBoundary>

      {/* Market Sentiment (L/S Ratio, News Velocity, SSR) */}
      <SectionErrorBoundary sectionName="Market Sentiment">
        <MarketSentimentPanel />
      </SectionErrorBoundary>

      {/* Market Intelligence + Earnings Calendar */}
      <SectionErrorBoundary sectionName="Market Intelligence">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <IntelligencePanel />
          </div>
          <EarningsCalendarPanel />
        </div>
      </SectionErrorBoundary>

      {/* Correlation + Funding Rates + Funding Arbitrage */}
      <SectionErrorBoundary sectionName="Correlation & Funding Rates">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
          <CorrelationPanel />
          <FundingRatePanel />
        </div>
      </SectionErrorBoundary>
      <SectionErrorBoundary sectionName="Funding Arbitrage">
        <FundingArbitragePanel onViewChart={handleSignalNavigate} />
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

      {/* Paper Trading Simulation */}
      <SectionErrorBoundary sectionName="Simulation">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
          <SimulationPanel onPositionClick={handlePositionClick} />
          <div data-section="bot-performance">
            <BotPerformancePanel />
          </div>
        </div>
      </SectionErrorBoundary>

      {/* Benchmark Comparison */}
      <SectionErrorBoundary sectionName="Benchmark Comparison">
        <BenchmarkPanel />
      </SectionErrorBoundary>

      {/* Analytics */}
      <SectionErrorBoundary sectionName="Analytics">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
          <EquityCurvePanel />
          <StrategyHeatmapPanel />
        </div>
      </SectionErrorBoundary>

      {/* Trade Duration + Entry Timing */}
      <SectionErrorBoundary sectionName="Trade Duration & Entry Timing">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
          <TradeDurationPanel />
          <EntryTimingHeatmapPanel />
        </div>
      </SectionErrorBoundary>

      {/* Attribution */}
      <SectionErrorBoundary sectionName="Attribution">
        <AttributionPanel />
      </SectionErrorBoundary>

      {/* Exposure Heatmap */}
      <SectionErrorBoundary sectionName="Exposure Heatmap">
        <ExposureHeatmapPanel />
      </SectionErrorBoundary>

      {/* Funding Heatmap */}
      <SectionErrorBoundary sectionName="Funding Heatmap">
        <FundingHeatmapPanel />
      </SectionErrorBoundary>

      {/* Live Readiness */}
      <SectionErrorBoundary sectionName="Live Readiness">
        <LiveReadinessPanel />
      </SectionErrorBoundary>

      {/* Signal History */}
      <SectionErrorBoundary sectionName="Signal History">
        <SignalHistoryPanel />
      </SectionErrorBoundary>

      {/* Notification History */}
      <SectionErrorBoundary sectionName="Notification History">
        <NotificationHistoryPanel />
      </SectionErrorBoundary>

      {/* Position Detail Drawer — rendered at root level to escape layout containers */}
      <PositionDetailDrawer
        position={focusedPosition}
        onClose={() => { setFocusedPosition(null); }}
        onNavigateToChart={handleDrawerNavigate}
      />

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
                    onChange={(e) => { setExportFormat(e.target.value as "csv" | "json"); }}
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
            {filteredSignals.length === 0 && (
              <div className="rounded-lg border border-border bg-surface p-8 text-center text-gray-500">
                {globalAssetFilter
                  ? `No signals matching "${globalAssetFilter}"`
                  : "No active signals — run AI Analysis above to generate signals"}
              </div>
            )}
            {[...filteredSignals].sort((a, b) => b.confidence - a.confidence).map((signal, i) => (
              <SignalCard
                key={signal.id}
                signal={signal}
                isNew={i === 0}
                isDuplicate={signalDupMap.get(signal.id) === true}
                onNavigate={handleSignalNavigate}
              />
            ))}
          </div>
        </SectionErrorBoundary>
        <SectionErrorBoundary sectionName="Risk & PnL">
          <div className="space-y-4">
            <RiskPanel
              systemStatus={systemPaused ? "PAUSED" : "ACTIVE"}
              drawdownPct={drawdownPct}
              maxDrawdownPct={settings?.max_drawdown_pct ?? 10}
              onResetKillSwitch={() => { void handleResetKillSwitch(); }}
            />
            <RecoveryProtocolWidget />
            <StreakCircuitBreakerWidget />
            <DrawdownBudgetWidget />
            <SpreadQualityWidget />
            <PnLSimulator />
          </div>
        </SectionErrorBoundary>
      </div>

      {/* End of dashboard tab */}
      </>}

      {/* Command Palette — global Cmd+K / Ctrl+K shortcut */}
      <CommandPalette
        onSelectSymbol={handleCommandPaletteSymbol}
        onStartBot={handleCommandPaletteStartBot}
        onStopBot={handleCommandPaletteStopBot}
      />

      <ShortcutsHelp open={showShortcutsHelp} onClose={() => { setShowShortcutsHelp(false); }} />
    </div>
  );
}
