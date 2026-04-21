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
 *
 * Usage:
 *   useHotkeys({
 *     onTimeframeChange: (tf) => setTf(tf),
 *     onFullscreen: () => toggleFullscreen(),
 *     onRefresh: () => queryClient.invalidateQueries(),
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

interface HotkeyHandlers {
  onTimeframeChange?: (tf: string) => void;
  onFullscreen?: () => void;
  onRefresh?: () => void;
  onLongBias?: () => void;
  onShortBias?: () => void;
  enabled?: boolean;
}

export function useHotkeys({
  onTimeframeChange,
  onFullscreen,
  onRefresh,
  onLongBias,
  onShortBias,
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

      // Skip Cmd/Ctrl combinations (reserved for browser/OS shortcuts)
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const key = e.key;

      // Timeframe switch: 1-6
      if (TIMEFRAME_MAP[key]) {
        e.preventDefault();
        onTimeframeChange?.(TIMEFRAME_MAP[key]);
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
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, onTimeframeChange, onFullscreen, onRefresh, onLongBias, onShortBias]);
}
