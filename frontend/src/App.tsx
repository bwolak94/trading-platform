import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { AgentPanel } from "./components/Dashboard/AgentPanel";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { FootprintChart } from "./components/Dashboard/FootprintChart";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { ToastProvider } from "./components/ui/Toast";
import { BacktestPage } from "./pages/Backtest";
import { ProAnalysisPage } from "./pages/ProAnalysis";
import { SettingsPage } from "./pages/Settings";
import { TradeHistoryPage } from "./pages/TradeHistory";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
    },
  },
});

type Page = "dashboard" | "orderflow" | "backtest" | "agent" | "settings" | "pro-analysis" | "history";

const PAGE_KEYS: Record<string, Page> = {
  "1": "dashboard",
  "2": "orderflow",
  "3": "backtest",
  "4": "agent",
  "5": "settings",
  "6": "pro-analysis",
  "7": "history",
};

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      )
        return;

      const target = PAGE_KEYS[e.key];
      if (target) {
        setPage(target);
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const navItems: { label: string; shortcut: string; page: Page }[] = [
    { label: "Dashboard", shortcut: "1", page: "dashboard" },
    { label: "Order Flow", shortcut: "2", page: "orderflow" },
    { label: "Backtest", shortcut: "3", page: "backtest" },
    { label: "AI Agent", shortcut: "4", page: "agent" },
    { label: "Settings", shortcut: "5", page: "settings" },
    { label: "Pro Analysis", shortcut: "6", page: "pro-analysis" },
    { label: "History", shortcut: "7", page: "history" },
  ];

  return (
    <ToastProvider>
      <QueryClientProvider client={queryClient}>
        <div className="min-h-screen bg-background">
          {/* Navigation */}
          <nav className="border-b border-border px-4 py-3 md:px-6">
            <div className="flex items-center justify-between gap-4 md:justify-start md:gap-6">
              <span className="text-lg font-bold text-white">
                AI Trading Navigator
              </span>

              {/* Mobile hamburger */}
              <button
                type="button"
                className="rounded p-1.5 text-gray-400 hover:bg-surface hover:text-white md:hidden"
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
            </ErrorBoundary>
          </main>
        </div>
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
      className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-surface text-white"
          : "text-gray-400 hover:bg-surface hover:text-white"
      }`}
      aria-label={`Navigate to ${label} (shortcut: ${shortcut})`}
    >
      {label}
      <span className="ml-1 text-[10px] text-gray-600">{shortcut}</span>
    </button>
  );
}

export default App;
