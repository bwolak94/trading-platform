import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "@/store";
import type { Signal, RegimeData } from "@/types";

// ── Fixtures ──────────────────────────────────────────────────────────────

const MOCK_SIGNAL: Signal = {
  id: "sig-001",
  asset: "BTCUSDT",
  direction: "LONG",
  confidence: 75,
  regime: "TREND_BULL",
  entry_price: 65000,
  stop_loss: 63000,
  take_profit_1: 68000,
  take_profit_2: null,
  risk_reward: 1.5,
  position_size_pct: 2,
  technical_score: 80,
  onchain_score: null,
  sentiment_score: null,
  macro_score: null,
  factors: [],
  status: "ACTIVE",
  expires_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const MOCK_REGIME: RegimeData = {
  asset: "BTCUSDT",
  regime: "TREND_BULL",
  confidence: 0.88,
  started_at: new Date().toISOString(),
  ended_at: null,
  metadata: null,
};

// Reset store between tests
beforeEach(() => {
  useAppStore.setState({
    activeSignals: [],
    regimes: [],
    settings: null,
    systemPaused: false,
    drawdownPct: 0,
    selectedAsset: "BTCUSDT",
    selectedTimeframe: "1h",
    enabledIndicators: [],
    activeMainTab: "dashboard",
  });
});

// ── Tests ─────────────────────────────────────────────────────────────────

describe("AppStore — signals", () => {
  it("initializes with empty activeSignals", () => {
    const { activeSignals } = useAppStore.getState();
    expect(activeSignals).toHaveLength(0);
  });

  it("setActiveSignals replaces the signal list", () => {
    const store = useAppStore.getState();
    store.setActiveSignals([MOCK_SIGNAL]);
    expect(useAppStore.getState().activeSignals).toHaveLength(1);
    expect(useAppStore.getState().activeSignals[0]!.id).toBe("sig-001");
  });

  it("addSignal prepends new signal to the list", () => {
    const store = useAppStore.getState();
    store.setActiveSignals([MOCK_SIGNAL]);

    const newSignal: Signal = { ...MOCK_SIGNAL, id: "sig-002" };
    useAppStore.getState().addSignal(newSignal);

    const { activeSignals } = useAppStore.getState();
    expect(activeSignals).toHaveLength(2);
    expect(activeSignals[0]!.id).toBe("sig-002");
    expect(activeSignals[1]!.id).toBe("sig-001");
  });

  it("setActiveSignals with empty array clears all signals", () => {
    const store = useAppStore.getState();
    store.setActiveSignals([MOCK_SIGNAL]);
    store.setActiveSignals([]);
    expect(useAppStore.getState().activeSignals).toHaveLength(0);
  });
});

describe("AppStore — regimes", () => {
  it("initializes with empty regimes", () => {
    expect(useAppStore.getState().regimes).toHaveLength(0);
  });

  it("setRegimes updates the regime list", () => {
    useAppStore.getState().setRegimes([MOCK_REGIME]);
    expect(useAppStore.getState().regimes).toHaveLength(1);
    expect(useAppStore.getState().regimes[0]!.regime).toBe("TREND_BULL");
  });

  it("setRegimes replaces previous regimes", () => {
    const store = useAppStore.getState();
    store.setRegimes([MOCK_REGIME]);
    store.setRegimes([{ ...MOCK_REGIME, asset: "ETHUSDT" }]);
    expect(useAppStore.getState().regimes).toHaveLength(1);
    expect(useAppStore.getState().regimes[0]!.asset).toBe("ETHUSDT");
  });
});

describe("AppStore — system state", () => {
  it("systemPaused defaults to false", () => {
    expect(useAppStore.getState().systemPaused).toBe(false);
  });

  it("setSystemPaused toggles the flag", () => {
    useAppStore.getState().setSystemPaused(true);
    expect(useAppStore.getState().systemPaused).toBe(true);
    useAppStore.getState().setSystemPaused(false);
    expect(useAppStore.getState().systemPaused).toBe(false);
  });

  it("drawdownPct defaults to 0", () => {
    expect(useAppStore.getState().drawdownPct).toBe(0);
  });

  it("setDrawdownPct updates the value", () => {
    useAppStore.getState().setDrawdownPct(12.5);
    expect(useAppStore.getState().drawdownPct).toBe(12.5);
  });
});

describe("AppStore — UI preferences", () => {
  it("selectedAsset defaults to BTCUSDT", () => {
    expect(useAppStore.getState().selectedAsset).toBe("BTCUSDT");
  });

  it("setSelectedAsset updates the asset", () => {
    useAppStore.getState().setSelectedAsset("ETHUSDT");
    expect(useAppStore.getState().selectedAsset).toBe("ETHUSDT");
  });

  it("selectedTimeframe defaults to 1h", () => {
    expect(useAppStore.getState().selectedTimeframe).toBe("1h");
  });

  it("setSelectedTimeframe updates the timeframe", () => {
    useAppStore.getState().setSelectedTimeframe("4h");
    expect(useAppStore.getState().selectedTimeframe).toBe("4h");
  });

  it("setEnabledIndicators stores indicator list", () => {
    useAppStore.getState().setEnabledIndicators(["EMA", "RSI", "MACD"]);
    expect(useAppStore.getState().enabledIndicators).toEqual(["EMA", "RSI", "MACD"]);
  });

  it("activeMainTab defaults to dashboard", () => {
    expect(useAppStore.getState().activeMainTab).toBe("dashboard");
  });

  it("setActiveMainTab switches to positioning", () => {
    useAppStore.getState().setActiveMainTab("positioning");
    expect(useAppStore.getState().activeMainTab).toBe("positioning");
  });
});
