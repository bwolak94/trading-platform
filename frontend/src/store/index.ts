import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RegimeData, Signal, UserSettings } from "../types";

interface AppState {
  // Signals
  activeSignals: Signal[];
  setActiveSignals: (signals: Signal[]) => void;
  addSignal: (signal: Signal) => void;

  // Regimes
  regimes: RegimeData[];
  setRegimes: (regimes: RegimeData[]) => void;

  // Settings
  settings: UserSettings | null;
  setSettings: (settings: UserSettings) => void;

  // System
  systemPaused: boolean;
  setSystemPaused: (paused: boolean) => void;
  drawdownPct: number;
  setDrawdownPct: (pct: number) => void;

  // UI Preferences (persisted)
  selectedAsset: string;
  setSelectedAsset: (asset: string) => void;
  selectedTimeframe: string;
  setSelectedTimeframe: (timeframe: string) => void;
  enabledIndicators: string[];
  setEnabledIndicators: (indicators: string[]) => void;

  // Main tab navigation (persisted)
  activeMainTab: "dashboard" | "positioning";
  setActiveMainTab: (tab: "dashboard" | "positioning") => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      activeSignals: [],
      setActiveSignals: (signals) => set({ activeSignals: signals }),
      addSignal: (signal) =>
        set((state) => ({
          activeSignals: [signal, ...state.activeSignals],
        })),

      regimes: [],
      setRegimes: (regimes) => set({ regimes }),

      settings: null,
      setSettings: (settings) => set({ settings }),

      systemPaused: false,
      setSystemPaused: (paused) => set({ systemPaused: paused }),
      drawdownPct: 0,
      setDrawdownPct: (pct) => set({ drawdownPct: pct }),

      selectedAsset: "BTCUSDT",
      setSelectedAsset: (asset) => set({ selectedAsset: asset }),
      selectedTimeframe: "4h",
      setSelectedTimeframe: (timeframe) => set({ selectedTimeframe: timeframe }),
      enabledIndicators: [],
      setEnabledIndicators: (indicators) =>
        set({ enabledIndicators: indicators }),

      activeMainTab: "dashboard",
      setActiveMainTab: (tab) => set({ activeMainTab: tab }),
    }),
    {
      name: "trading-platform-store",
      partialize: (state) => ({
        selectedAsset: state.selectedAsset,
        selectedTimeframe: state.selectedTimeframe,
        enabledIndicators: state.enabledIndicators,
        activeMainTab: state.activeMainTab,
      }),
    }
  )
);
