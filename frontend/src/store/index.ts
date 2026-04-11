import { create } from "zustand";
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
}

export const useAppStore = create<AppState>((set) => ({
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
}));
