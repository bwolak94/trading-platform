import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WebSocketProvider } from "./contexts/WebSocketContext";
import { useState, useEffect, useCallback, useRef } from "react";
import { AgentPanel } from "./components/Dashboard/AgentPanel";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { FootprintChart } from "./components/Dashboard/FootprintChart";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { ToastProvider } from "./components/ui/Toast";
import { useTheme } from "./hooks/useTheme";
import { BacktestPage } from "./pages/Backtest";
import { ProAnalysisPage } from "./pages/ProAnalysis";
import { SettingsPage } from "./pages/Settings";
import { ScreenerPage } from "./pages/Screener";
import { TradeHistoryPage } from "./pages/TradeHistory";

// A8: gcTime extended to 10 min so long-lived tabs retain data in memory and
// avoid redundant refetches (default is 5 min).
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 10 * 60 * 1000,
      retry: 2,
    },
  },
});

type Page = "dashboard" | "orderflow" | "backtest" | "agent" | "settings" | "pro-analysis" | "history" | "screener";

const PAGE_KEYS: Record<string, Page> = {
  "1": "dashboard",
  "2": "orderflow",
  "3": "backtest",
  "4": "agent",
  "5": "settings",
  "6": "pro-analysis",
  "7": "history",
  "8": "screener",
};

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const toggleShortcuts = useCallback(() => setShowShortcuts((prev) => !prev), []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      )
        return;

      if (e.key === "Escape" && showShortcuts) {
        setShowShortcuts(false);
        return;
      }

      if (e.key === "?") {
        setShowShortcuts((prev) => !prev);
        return;
      }

      const target = PAGE_KEYS[e.key];
      if (target) {
        setPage(target);
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showShortcuts]);

  const navItems: { label: string; shortcut: string; page: Page }[] = [
    { label: "Dashboard", shortcut: "1", page: "dashboard" },
    { label: "Order Flow", shortcut: "2", page: "orderflow" },
    { label: "Backtest", shortcut: "3", page: "backtest" },
    { label: "AI Agent", shortcut: "4", page: "agent" },
    { label: "Settings", shortcut: "5", page: "settings" },
    { label: "Pro Analysis", shortcut: "6", page: "pro-analysis" },
    { label: "History", shortcut: "7", page: "history" },
    { label: "Screener", shortcut: "8", page: "screener" },
  ];

  return (
    <ToastProvider>
      <QueryClientProvider client={queryClient}>
      <WebSocketProvider>
        <div className="min-h-screen bg-background">
          {/* Navigation */}
          <nav className="border-b border-border px-4 py-3 md:px-6">
            <div className="flex items-center justify-between gap-4 md:justify-start md:gap-6">
              <span className="text-lg font-bold text-foreground">
                AI Trading Navigator
              </span>

              {/* Keyboard shortcuts button */}
              <button
                type="button"
                onClick={toggleShortcuts}
                className="min-h-[44px] min-w-[44px] rounded p-1.5 text-gray-400 hover:bg-surface hover:text-foreground transition-colors font-bold text-lg"
                aria-label="Show keyboard shortcuts"
                title="Keyboard shortcuts (?)"
              >
                ?
              </button>

              {/* Theme toggle */}
              <button
                type="button"
                onClick={toggleTheme}
                className="min-h-[44px] min-w-[44px] rounded p-1.5 text-gray-400 hover:bg-surface hover:text-foreground transition-colors"
                aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              >
                {theme === "dark" ? (
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
                  </svg>
                ) : (
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
                  </svg>
                )}
              </button>

              {/* Mobile hamburger */}
              <button
                type="button"
                className="rounded p-1.5 text-muted hover:bg-surface hover:text-foreground md:hidden"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                aria-label={mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
                aria-expanded={mobileMenuOpen}
              >
                <svg
                  className="h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                >
                  {mobileMenuOpen ? (
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                  )}
                </svg>
              </button>

              {/* Desktop nav - horizontal scroll on medium screens */}
              <div className="hidden overflow-x-auto md:flex md:gap-1">
                {navItems.map((item) => (
                  <NavButton
                    key={item.page}
                    label={item.label}
                    shortcut={item.shortcut}
                    active={page === item.page}
                    onClick={() => setPage(item.page)}
                  />
                ))}
              </div>
            </div>

            {/* Mobile dropdown menu */}
            {mobileMenuOpen && (
              <div className="mt-3 flex flex-col gap-1 border-t border-border pt-3 md:hidden">
                {navItems.map((item) => (
                  <NavButton
                    key={item.page}
                    label={item.label}
                    shortcut={item.shortcut}
                    active={page === item.page}
                    onClick={() => {
                      setPage(item.page);
                      setMobileMenuOpen(false);
                    }}
                  />
                ))}
              </div>
            )}
          </nav>

          {/* Content */}
          <main className="mx-auto max-w-7xl p-4 md:p-6">
            <ErrorBoundary>
              {page === "dashboard" && <Dashboard />}
              {page === "orderflow" && <FootprintChart />}
              {page === "backtest" && <BacktestPage />}
              {page === "agent" && <AgentPanel />}
              {page === "settings" && <SettingsPage />}
              {page === "pro-analysis" && <ProAnalysisPage />}
              {page === "history" && <TradeHistoryPage />}
              {page === "screener" && <ScreenerPage />}
            </ErrorBoundary>
          </main>

          {/* Keyboard shortcuts modal */}
          {showShortcuts && (
            <ShortcutsModal onClose={() => setShowShortcuts(false)} navItems={navItems} />
          )}
        </div>
      </WebSocketProvider>
      </QueryClientProvider>
    </ToastProvider>
  );
}

function NavButton({
  label,
  shortcut,
  active,
  onClick,
}: {
  label: string;
  shortcut: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`min-h-[44px] rounded px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-surface text-foreground"
          : "text-muted hover:bg-surface hover:text-foreground"
      }`}
      aria-label={`Navigate to ${label} (shortcut: ${shortcut})`}
    >
      {label}
      <span className="ml-1 text-[10px] text-gray-600">{shortcut}</span>
    </button>
  );
}

function ShortcutsModal({
  onClose,
  navItems,
}: {
  onClose: () => void;
  navItems: { label: string; shortcut: string; page: string }[];
}) {
  const overlayRef = useRef<HTMLDivElement>(null);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === overlayRef.current) onClose();
    },
    [onClose]
  );

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div className="mx-4 w-full max-w-md rounded-lg border border-border bg-surface p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-foreground">Keyboard Shortcuts</h2>
          <button
            type="button"
            onClick={onClose}
            className="min-h-[44px] min-w-[44px] rounded p-1 text-gray-400 hover:text-foreground transition-colors"
            aria-label="Close shortcuts modal"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-1">
          <p className="mb-3 text-xs text-gray-500 uppercase tracking-wide font-medium">Page Navigation</p>
          {navItems.map((item) => (
            <div key={item.shortcut} className="flex items-center justify-between py-1.5">
              <span className="text-sm text-gray-300">{item.label}</span>
              <kbd className="rounded bg-background px-2 py-1 font-mono text-xs text-gray-400 border border-border">
                {item.shortcut}
              </kbd>
            </div>
          ))}

          <div className="my-3 border-t border-border" />
          <p className="mb-3 text-xs text-gray-500 uppercase tracking-wide font-medium">General</p>

          <div className="flex items-center justify-between py-1.5">
            <span className="text-sm text-gray-300">Show / hide this dialog</span>
            <kbd className="rounded bg-background px-2 py-1 font-mono text-xs text-gray-400 border border-border">
              ?
            </kbd>
          </div>
          <div className="flex items-center justify-between py-1.5">
            <span className="text-sm text-gray-300">Close dialog / modal</span>
            <kbd className="rounded bg-background px-2 py-1 font-mono text-xs text-gray-400 border border-border">
              Esc
            </kbd>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
