/**
 * Layout Presets — predefined dashboard configurations.
 *
 * Presets:
 *   - Day Trading:    Charts, OrderFlow, DayTradeHUD, LiveRegime, Signals
 *   - Swing Trading:  MultiChart, Signals, Analysis, Regime, MacroPanel
 *   - Risk Monitor:   Equity, Drawdown, VaR, Simulation, Correlation
 *   - Research:       Analysis, Intelligence, Backtest, Pro Analysis
 *
 * Usage:
 *   const { activePreset, applyPreset } = useLayoutPreset();
 *   <LayoutPresets onApplyPreset={applyPreset} activePreset={activePreset} />
 */

import { useState, useCallback } from "react";

// --------------- Types ---------------

export type LayoutPreset = "day_trading" | "swing_trading" | "risk_monitor" | "research";

interface PresetDefinition {
  label: string;
  icon: string;
  description: string;
  panels: string[];
}

interface LayoutPresetsProps {
  onApplyPreset: (preset: LayoutPreset) => void;
  activePreset?: LayoutPreset | null;
}

// --------------- Preset definitions ---------------

export const PRESETS: Record<LayoutPreset, PresetDefinition> = {
  day_trading: {
    label: "Day Trading",
    icon: "⚡",
    description: "Charts, order flow, live signals and day trading HUD",
    panels: ["chart", "orderflow", "signals", "regime", "daytrade_hud"],
  },
  swing_trading: {
    label: "Swing Trading",
    icon: "📈",
    description: "Multi-chart analysis, signals, regime and macro panel",
    panels: ["multichart", "signals", "analysis", "regime", "macro"],
  },
  risk_monitor: {
    label: "Risk Monitor",
    icon: "🛡",
    description: "Portfolio risk, exposure, simulation and correlation",
    panels: ["equity", "simulation", "correlation", "risk", "montecarlo"],
  },
  research: {
    label: "Research",
    icon: "🔬",
    description: "Deep analysis, intelligence panel and backtesting",
    panels: ["analysis", "intelligence", "attribution", "strategy_stats"],
  },
};

// --------------- LayoutPresets component ---------------

/**
 * A row of preset buttons. Pressing a button calls `onApplyPreset` with the
 * corresponding `LayoutPreset` key. The active preset is visually highlighted.
 */
export function LayoutPresets({ onApplyPreset, activePreset }: LayoutPresetsProps) {
  return (
    <div
      className="flex gap-2 flex-wrap"
      role="group"
      aria-label="Dashboard layout presets"
    >
      {(Object.entries(PRESETS) as [LayoutPreset, PresetDefinition][]).map(([key, preset]) => {
        const isActive = activePreset === key;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onApplyPreset(key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors
              ${
                isActive
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border bg-surface text-gray-400 hover:border-accent/50 hover:text-gray-200"
              }`}
            aria-pressed={isActive}
            title={preset.description}
            aria-label={`${isActive ? "Active: " : ""}${preset.label} layout — ${preset.description}`}
          >
            <span aria-hidden="true">{preset.icon}</span>
            <span>{preset.label}</span>
          </button>
        );
      })}
    </div>
  );
}

// --------------- useLayoutPreset hook ---------------

const STORAGE_KEY = "layout_preset";

/**
 * Manages the active layout preset with localStorage persistence.
 *
 * @returns `activePreset` — the currently active preset key (or null)
 * @returns `applyPreset`  — call to switch to a new preset
 * @returns `clearPreset`  — call to reset to no active preset
 * @returns `activePanels` — the panel list for the active preset
 */
export function useLayoutPreset(): {
  activePreset: LayoutPreset | null;
  applyPreset: (preset: LayoutPreset) => void;
  clearPreset: () => void;
  activePanels: string[];
} {
  const [activePreset, setActivePreset] = useState<LayoutPreset | null>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && Object.keys(PRESETS).includes(stored)) {
        return stored as LayoutPreset;
      }
    } catch {
      // localStorage unavailable
    }
    return null;
  });

  const applyPreset = useCallback((preset: LayoutPreset): void => {
    setActivePreset(preset);
    try {
      localStorage.setItem(STORAGE_KEY, preset);
    } catch {
      // localStorage unavailable
    }
  }, []);

  const clearPreset = useCallback((): void => {
    setActivePreset(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // localStorage unavailable
    }
  }, []);

  const activePanels: string[] = activePreset ? PRESETS[activePreset].panels : [];

  return { activePreset, applyPreset, clearPreset, activePanels };
}
