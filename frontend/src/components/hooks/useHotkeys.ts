/**
 * Keyboard Shortcuts System — global hotkeys for the trading dashboard.
 *
 * Shortcuts:
 *   Cmd/Ctrl+K  → Command Palette (handled in CommandPalette directly)
 *   F           → Toggle fullscreen
 *   Esc         → Close modals (handled per modal)
 *   1–6         → Switch timeframe (1m, 5m, 15m, 1h, 4h, 1d)
 *   B           → Set LONG / Buy bias
 *   S           → Set SHORT / Sell bias
 *   R           → Refresh data
 *   N           → Next signal
 *   P           → Previous signal
 *   E           → Explain focused signal (XAI)
 *   J           → Open trade journal
 *   T           → Toggle theme
 *   Tab         → Toggle sidebar
 *   ?           → Show shortcuts help
 *
 * Usage:
 *   useHotkeys({
 *     onTimeframeChange: (tf) => setTf(tf),
 *     onFullscreen: () => toggleFullscreen(),
 *     onRefresh: () => queryClient.invalidateQueries(),
 *     onNextSignal: () => goToNextSignal(),
 *     onPrevSignal: () => goToPrevSignal(),
 *   });
 */

import { useEffect } from "react";

const TIMEFRAME_MAP: Record<string, string> = {
  "1": "1m",
  "2": "5m",
  "3": "15m",
  "4": "1h",
  "5": "4h",
  "6": "1d",
};

export interface HotkeyHandlers {
  onTimeframeChange?: (tf: string) => void;
  onFullscreen?: () => void;
  onRefresh?: () => void;
  onLongBias?: () => void;
  onShortBias?: () => void;
  /** N key — navigate to next signal in the list */
  onNextSignal?: () => void;
  /** P key — navigate to previous signal in the list */
  onPrevSignal?: () => void;
  /** E key — trigger XAI explanation for the currently focused signal */
  onExplainSignal?: () => void;
  /** J key — open the trade journal panel/page */
  onOpenJournal?: () => void;
  /** T key — toggle between dark / light / terminal themes */
  onToggleTheme?: () => void;
  /** Tab key — toggle the sidebar panel visibility */
  onToggleSidebar?: () => void;
  /** ? key — show the keyboard shortcuts help overlay */
  onShowHelp?: () => void;
  enabled?: boolean;
}

export function useHotkeys({
  onTimeframeChange,
  onFullscreen,
  onRefresh,
  onLongBias,
  onShortBias,
  onNextSignal,
  onPrevSignal,
  onExplainSignal,
  onOpenJournal,
  onToggleTheme,
  onToggleSidebar,
  onShowHelp,
  enabled = true,
}: HotkeyHandlers): void {
  useEffect(() => {
    if (!enabled) return;

    function handleKeyDown(e: KeyboardEvent): void {
      // Skip when user is typing in an input field
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      // Skip Cmd/Ctrl/Alt combinations (reserved for browser/OS shortcuts)
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const key = e.key;

      // Timeframe switch: 1-6
      if (TIMEFRAME_MAP[key]) {
        e.preventDefault();
        onTimeframeChange?.(TIMEFRAME_MAP[key]);
        return;
      }

      // Tab key — toggle sidebar (must check before lower() to avoid collision)
      if (key === "Tab") {
        e.preventDefault();
        onToggleSidebar?.();
        return;
      }

      // ? key — show help (Shift+/ on most keyboards sends "?")
      if (key === "?") {
        e.preventDefault();
        onShowHelp?.();
        return;
      }

      switch (key.toLowerCase()) {
        case "f":
          e.preventDefault();
          onFullscreen?.();
          if (document.fullscreenElement) {
            void document.exitFullscreen();
          } else {
            void document.documentElement.requestFullscreen();
          }
          break;
        case "r":
          e.preventDefault();
          onRefresh?.();
          break;
        case "b":
          e.preventDefault();
          onLongBias?.();
          break;
        case "s":
          e.preventDefault();
          onShortBias?.();
          break;
        case "n":
          e.preventDefault();
          onNextSignal?.();
          break;
        case "p":
          e.preventDefault();
          onPrevSignal?.();
          break;
        case "e":
          e.preventDefault();
          onExplainSignal?.();
          break;
        case "j":
          e.preventDefault();
          onOpenJournal?.();
          break;
        case "t":
          e.preventDefault();
          onToggleTheme?.();
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    enabled,
    onTimeframeChange,
    onFullscreen,
    onRefresh,
    onLongBias,
    onShortBias,
    onNextSignal,
    onPrevSignal,
    onExplainSignal,
    onOpenJournal,
    onToggleTheme,
    onToggleSidebar,
    onShowHelp,
  ]);
}
