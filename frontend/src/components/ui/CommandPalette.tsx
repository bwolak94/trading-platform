import { useCallback, useEffect, useRef, useState } from "react";

// --------------- Types ---------------

type CommandCategory = "navigation" | "action" | "symbol" | "assets";

interface Command {
  id: string;
  label: string;
  description?: string;
  category: CommandCategory;
  keywords: string[];
  icon?: string;
  shortcut?: string;
  action: () => void;
}

interface CommandPaletteProps {
  onSelectSymbol?: (symbol: string) => void;
  onStartBot?: () => void;
  onStopBot?: () => void;
  /** Generic command execution handler for built-in commands */
  onCommand?: (commandId: string) => void;
}

// --------------- Constants ---------------

const POPULAR_SYMBOLS = [
  "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
  "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
];

const CATEGORY_LABEL: Record<CommandCategory, string> = {
  symbol: "Symbols",
  action: "Actions",
  navigation: "Navigate",
  assets: "Assets",
};

const RECENT_COMMANDS_KEY = "cmd_palette_recent";
const MAX_RECENT = 5;

// --------------- Fuzzy search ---------------

/**
 * Simple fuzzy-match: all query characters must appear in the target string
 * in order. Returns a numeric score (higher = better match).
 */
function fuzzyScore(query: string, target: string): number {
  const q = query.toLowerCase();
  const t = target.toLowerCase();
  if (t.includes(q)) return 100 + (100 - t.indexOf(q)); // exact substring bonus
  let qi = 0;
  let score = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      qi++;
      score += 10;
    }
  }
  return qi === q.length ? score : 0;
}

function fuzzyMatch(query: string, cmd: Command): number {
  if (!query.trim()) return 1;
  const sources = [cmd.label, cmd.description ?? "", ...cmd.keywords];
  return Math.max(...sources.map((s) => fuzzyScore(query, s)));
}

// --------------- Recent commands storage ---------------

function loadRecentCommandIds(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_COMMANDS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((x) => typeof x === "string")) {
      return parsed as string[];
    }
    return [];
  } catch {
    return [];
  }
}

function saveRecentCommandId(id: string): void {
  const existing = loadRecentCommandIds().filter((r) => r !== id);
  const updated = [id, ...existing].slice(0, MAX_RECENT);
  try {
    localStorage.setItem(RECENT_COMMANDS_KEY, JSON.stringify(updated));
  } catch {
    // localStorage may be unavailable in some contexts
  }
}

// --------------- CommandPalette ---------------

export function CommandPalette({ onSelectSymbol, onStartBot, onStopBot, onCommand }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [recentIds, setRecentIds] = useState<string[]>(() => loadRecentCommandIds());
  const inputRef = useRef<HTMLInputElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setSelectedIndex(0);
  }, []);

  const executeCommand = useCallback((cmd: Command) => {
    saveRecentCommandId(cmd.id);
    setRecentIds(loadRecentCommandIds());
    cmd.action();
  }, []);

  const getCommands = useCallback((): Command[] => {
    const commands: Command[] = [
      // ---- Assets category ----
      ...POPULAR_SYMBOLS.map((sym) => ({
        id: `symbol-${sym}`,
        label: sym.replace("USDT", "/USDT"),
        description: "Navigate to symbol chart",
        category: "assets" as const,
        keywords: [sym.toLowerCase(), sym.replace("USDT", "").toLowerCase(), "chart", "symbol"],
        icon: "📈",
        action: () => {
          onSelectSymbol?.(sym);
          onCommand?.(`symbol-${sym}`);
          close();
        },
      })),
      // ---- Navigation category ----
      {
        id: "nav-btc-chart",
        label: "Go to BTC chart",
        description: "Navigate chart to BTCUSDT",
        category: "navigation",
        keywords: ["btc", "bitcoin", "chart", "navigate"],
        icon: "₿",
        action: () => {
          onSelectSymbol?.("BTCUSDT");
          onCommand?.("nav-btc-chart");
          close();
        },
      },
      {
        id: "nav-eth-chart",
        label: "Go to ETH chart",
        description: "Navigate chart to ETHUSDT",
        category: "navigation",
        keywords: ["eth", "ethereum", "chart", "navigate"],
        icon: "Ξ",
        action: () => {
          onSelectSymbol?.("ETHUSDT");
          onCommand?.("nav-eth-chart");
          close();
        },
      },
      {
        id: "nav-backtest",
        label: "Run Backtest",
        description: "Open backtesting page",
        category: "navigation",
        keywords: ["backtest", "test", "simulate", "historical"],
        icon: "🧪",
        shortcut: undefined,
        action: () => {
          onCommand?.("nav-backtest");
          close();
        },
      },
      {
        id: "nav-screener",
        label: "Open Screener",
        description: "Open market screener page",
        category: "navigation",
        keywords: ["screener", "scan", "filter", "market"],
        icon: "🔍",
        action: () => {
          onCommand?.("nav-screener");
          close();
        },
      },
      {
        id: "nav-journal",
        label: "Open Journal",
        description: "Navigate to trade journal",
        category: "navigation",
        keywords: ["journal", "trades", "log", "diary"],
        icon: "📓",
        shortcut: "J",
        action: () => {
          onCommand?.("nav-journal");
          close();
        },
      },
      {
        id: "nav-equity",
        label: "Equity Curve",
        description: "Scroll to bot performance panel",
        category: "navigation",
        keywords: ["equity", "curve", "performance", "pnl", "chart", "bot"],
        icon: "📊",
        action: () => {
          document
            .querySelector("[data-section='bot-performance']")
            ?.scrollIntoView({ behavior: "smooth" });
          onCommand?.("nav-equity");
          close();
        },
      },
      // ---- Actions category ----
      {
        id: "action-refresh",
        label: "Refresh Signals",
        description: "Trigger a full signal refresh",
        category: "action",
        keywords: ["refresh", "reload", "update", "signals"],
        icon: "🔄",
        shortcut: "R",
        action: () => {
          onCommand?.("action-refresh");
          close();
        },
      },
      {
        id: "action-toggle-theme",
        label: "Toggle Theme",
        description: "Switch between dark / light / terminal themes",
        category: "action",
        keywords: ["theme", "dark", "light", "toggle", "terminal"],
        icon: "🎨",
        shortcut: "T",
        action: () => {
          onCommand?.("action-toggle-theme");
          close();
        },
      },
      {
        id: "start-bot",
        label: "Start Paper Trading Bot",
        description: "Start the simulation engine",
        category: "action",
        keywords: ["start", "bot", "simulation", "paper", "trading"],
        icon: "▶",
        action: () => {
          onStartBot?.();
          onCommand?.("start-bot");
          close();
        },
      },
      {
        id: "stop-bot",
        label: "Stop Paper Trading Bot",
        description: "Stop the simulation engine",
        category: "action",
        keywords: ["stop", "bot", "simulation", "pause"],
        icon: "⏹",
        action: () => {
          onStopBot?.();
          onCommand?.("stop-bot");
          close();
        },
      },
      {
        id: "fullscreen",
        label: "Toggle Fullscreen",
        description: "Enter or exit fullscreen mode",
        category: "action",
        keywords: ["fullscreen", "full", "screen", "expand"],
        icon: "⛶",
        shortcut: "F",
        action: () => {
          if (document.fullscreenElement) {
            void document.exitFullscreen();
          } else {
            void document.documentElement.requestFullscreen();
          }
          onCommand?.("fullscreen");
          close();
        },
      },
    ];

    return commands;
  }, [onSelectSymbol, onStartBot, onStopBot, onCommand, close]);

  const allCommands = getCommands();

  /** Filter + sort commands by fuzzy score, grouped by category. */
  const filteredCommands: Command[] = (() => {
    if (!query.trim()) {
      // Show recents first, then default list capped at 8
      const recentCmds = recentIds
        .map((id) => allCommands.find((c) => c.id === id))
        .filter((c): c is Command => c !== undefined);
      const nonRecent = allCommands.filter((c) => !recentIds.includes(c.id)).slice(0, 8 - recentCmds.length);
      return [...recentCmds, ...nonRecent];
    }

    return allCommands
      .map((cmd) => ({ cmd, score: fuzzyMatch(query, cmd) }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score)
      .map(({ cmd }) => cmd);
  })();

  // Group by category
  const grouped: Map<CommandCategory, Command[]> = new Map();
  const categoryOrder: CommandCategory[] = ["navigation", "action", "assets", "symbol"];

  // Preserve category order
  for (const cat of categoryOrder) {
    const items = filteredCommands.filter((c) => c.category === cat);
    if (items.length > 0) grouped.set(cat, items);
  }
  // Catch any categories not in the predefined order
  for (const cmd of filteredCommands) {
    if (!categoryOrder.includes(cmd.category)) {
      const existing = grouped.get(cmd.category) ?? [];
      grouped.set(cmd.category, [...existing, cmd]);
    }
  }

  // Flat list for keyboard navigation indexing
  const flatCommands: Command[] = [...grouped.values()].flat();

  // Global Cmd+K / Ctrl+K toggle
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => {
          if (prev) {
            setQuery("");
            setSelectedIndex(0);
          }
          return !prev;
        });
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      const id = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(id);
    }
  }, [open]);

  // Navigation + Escape within palette
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        close();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, flatCommands.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const cmd = flatCommands[selectedIndex];
        if (cmd) executeCommand(cmd);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, flatCommands, selectedIndex, close, executeCommand]);

  // Reset selection when query changes
  useEffect(() => setSelectedIndex(0), [query]);

  if (!open) return null;

  // Track flat index offset as we render groups
  let globalIndex = 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[15vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={close}
        aria-hidden="true"
      />

      {/* Palette */}
      <div className="relative w-full max-w-lg overflow-hidden rounded-xl border border-border bg-background shadow-2xl">
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <span className="text-muted-foreground select-none" aria-hidden="true">⌘</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search commands, symbols..."
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            aria-label="Search commands"
            aria-autocomplete="list"
            aria-controls="command-palette-list"
            aria-activedescendant={
              flatCommands[selectedIndex] ? `cmd-${flatCommands[selectedIndex].id}` : undefined
            }
          />
          <kbd className="hidden rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground sm:block">
            ESC
          </kbd>
        </div>

        {/* Recent commands label (only when no query) */}
        {!query.trim() && recentIds.length > 0 && (
          <div className="px-4 pt-2 pb-0.5">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Recent</p>
          </div>
        )}

        {/* Results grouped by category */}
        <div
          id="command-palette-list"
          role="listbox"
          className="max-h-80 overflow-y-auto py-2"
          aria-label="Commands"
        >
          {flatCommands.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              No commands found for &quot;{query}&quot;
            </div>
          ) : (
            [...grouped.entries()].map(([category, cmds]) => {
              const section = (
                <div key={category}>
                  {/* Category header */}
                  <div className="px-4 pb-0.5 pt-2 first:pt-0" aria-hidden="true">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                      {CATEGORY_LABEL[category] ?? category}
                    </p>
                  </div>

                  {cmds.map((cmd) => {
                    const idx = globalIndex;
                    globalIndex += 1;
                    const isSelected = idx === selectedIndex;

                    return (
                      <div
                        key={cmd.id}
                        id={`cmd-${cmd.id}`}
                        role="option"
                        aria-selected={isSelected}
                        className={`flex cursor-pointer items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                          isSelected
                            ? "bg-accent text-accent-foreground"
                            : "text-foreground hover:bg-accent/50"
                        }`}
                        onMouseEnter={() => setSelectedIndex(idx)}
                        onClick={() => executeCommand(cmd)}
                      >
                        {cmd.icon && (
                          <span className="w-5 shrink-0 text-center text-base" aria-hidden="true">
                            {cmd.icon}
                          </span>
                        )}
                        <div className="flex min-w-0 flex-col gap-0.5">
                          <span className="truncate font-medium leading-none">{cmd.label}</span>
                          {cmd.description && (
                            <span className="truncate text-xs text-muted-foreground">{cmd.description}</span>
                          )}
                        </div>
                        {cmd.shortcut && (
                          <kbd
                            className="ml-auto shrink-0 rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground"
                            aria-label={`Shortcut: ${cmd.shortcut}`}
                          >
                            {cmd.shortcut}
                          </kbd>
                        )}
                        {!cmd.shortcut && (
                          <span className="ml-auto shrink-0 text-xs text-muted-foreground/40">
                            {CATEGORY_LABEL[cmd.category]}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
              return section;
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 border-t border-border px-4 py-2 text-xs text-muted-foreground">
          <span>
            <kbd className="rounded border border-border px-1 py-0.5">↑↓</kbd> Navigate
          </span>
          <span>
            <kbd className="rounded border border-border px-1 py-0.5">↵</kbd> Select
          </span>
          <span>
            <kbd className="rounded border border-border px-1 py-0.5">ESC</kbd> Close
          </span>
          <span className="ml-auto opacity-60">⌘K to toggle</span>
        </div>
      </div>
    </div>
  );
}
