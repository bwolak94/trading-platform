import { useCallback, useEffect, useRef, useState } from "react";

interface Command {
  id: string;
  label: string;
  description?: string;
  category: "navigation" | "action" | "symbol";
  keywords: string[];
  icon?: string;
  action: () => void;
}

interface CommandPaletteProps {
  onSelectSymbol?: (symbol: string) => void;
  onStartBot?: () => void;
  onStopBot?: () => void;
}

const POPULAR_SYMBOLS = [
  "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
  "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
];

const CATEGORY_LABEL: Record<Command["category"], string> = {
  symbol: "Symbols",
  action: "Actions",
  navigation: "Navigation",
};

export function CommandPalette({ onSelectSymbol, onStartBot, onStopBot }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setSelectedIndex(0);
  }, []);

  const getCommands = useCallback((): Command[] => {
    const commands: Command[] = [
      // Symbols
      ...POPULAR_SYMBOLS.map((sym) => ({
        id: `symbol-${sym}`,
        label: sym.replace("USDT", "/USDT"),
        description: "Navigate to symbol chart",
        category: "symbol" as const,
        keywords: [sym.toLowerCase(), sym.replace("USDT", "").toLowerCase()],
        icon: "📈",
        action: () => {
          onSelectSymbol?.(sym);
          close();
        },
      })),
      // Actions
      {
        id: "start-bot",
        label: "Start Paper Trading Bot",
        description: "Start the simulation engine",
        category: "action",
        keywords: ["start", "bot", "simulation", "paper", "trading"],
        icon: "▶",
        action: () => {
          onStartBot?.();
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
          close();
        },
      },
      {
        id: "equity-curve",
        label: "Equity Curve",
        description: "Scroll to bot performance panel",
        category: "navigation",
        keywords: ["equity", "curve", "performance", "pnl", "chart", "bot"],
        icon: "📊",
        action: () => {
          document
            .querySelector("[data-section='bot-performance']")
            ?.scrollIntoView({ behavior: "smooth" });
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
        action: () => {
          if (document.fullscreenElement) {
            void document.exitFullscreen();
          } else {
            void document.documentElement.requestFullscreen();
          }
          close();
        },
      },
    ];

    if (!query.trim()) return commands.slice(0, 8);

    const q = query.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.description?.toLowerCase().includes(q) ||
        cmd.keywords.some((k) => k.includes(q)),
    );
  }, [query, onSelectSymbol, onStartBot, onStopBot, close]);

  const commands = getCommands();

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
        setSelectedIndex((i) => Math.min(i + 1, commands.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        commands[selectedIndex]?.action();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, commands, selectedIndex, close]);

  // Reset selection when query changes
  useEffect(() => setSelectedIndex(0), [query]);

  if (!open) return null;

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
              commands[selectedIndex] ? `cmd-${commands[selectedIndex].id}` : undefined
            }
          />
          <kbd className="hidden rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground sm:block">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <ul
          id="command-palette-list"
          role="listbox"
          className="max-h-72 overflow-y-auto py-2"
          aria-label="Commands"
        >
          {commands.length === 0 ? (
            <li className="px-4 py-6 text-center text-sm text-muted-foreground">
              No commands found for &quot;{query}&quot;
            </li>
          ) : (
            commands.map((cmd, idx) => (
              <li
                key={cmd.id}
                id={`cmd-${cmd.id}`}
                role="option"
                aria-selected={idx === selectedIndex}
                className={`flex cursor-pointer items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  idx === selectedIndex
                    ? "bg-accent text-accent-foreground"
                    : "text-foreground hover:bg-accent/50"
                }`}
                onMouseEnter={() => setSelectedIndex(idx)}
                onClick={() => cmd.action()}
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
                <span className="ml-auto shrink-0 text-xs text-muted-foreground/60">
                  {CATEGORY_LABEL[cmd.category]}
                </span>
              </li>
            ))
          )}
        </ul>

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
