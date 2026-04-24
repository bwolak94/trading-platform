/**
 * Theme Hook — manages dark / light / terminal theme switching.
 * Persists preference to localStorage and applies a `data-theme` attribute
 * on `document.documentElement`.
 *
 * Terminal theme: green-on-black Matrix style using CSS variables defined in
 * index.css under the `[data-theme="terminal"]` selector.
 */

import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light" | "terminal";

const STORAGE_KEY = "trading-theme";
const DEFAULT_THEME: Theme = "dark";

function resolveInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored === "dark" || stored === "light" || stored === "terminal") {
      return stored;
    }
  } catch {
    // ignore
  }
  return DEFAULT_THEME;
}

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "dark") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", theme);
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(resolveInitialTheme);

  // Apply theme on mount and whenever it changes
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
    setThemeState(next);
  }, []);

  const cycleTheme = useCallback(() => {
    setThemeState((prev) => {
      const order: Theme[] = ["dark", "light", "terminal"];
      const nextIndex = (order.indexOf(prev) + 1) % order.length;
      const next = order[nextIndex]!;
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  return { theme, setTheme, cycleTheme };
}
