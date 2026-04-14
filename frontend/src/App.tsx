import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { AgentPanel } from "./components/Dashboard/AgentPanel";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { FootprintChart } from "./components/Dashboard/FootprintChart";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { ToastProvider } from "./components/ui/Toast";
import { BacktestPage } from "./pages/Backtest";
import { SettingsPage } from "./pages/Settings";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
    },
  },
});

type Page = "dashboard" | "orderflow" | "backtest" | "agent" | "settings";

const PAGE_KEYS: Record<string, Page> = {
  "1": "dashboard",
  "2": "orderflow",
  "3": "backtest",
  "4": "agent",
  "5": "settings",
};

function App() {
  const [page, setPage] = useState<Page>("dashboard");

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
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <ToastProvider>
      <QueryClientProvider client={queryClient}>
        <div className="min-h-screen bg-background">
          {/* Navigation */}
          <nav className="border-b border-border px-6 py-3">
            <div className="flex items-center gap-6">
              <span className="text-lg font-bold text-white">
                AI Trading Navigator
              </span>
              <div className="flex gap-1">
                <NavButton
                  label="Dashboard"
                  shortcut="1"
                  active={page === "dashboard"}
                  onClick={() => setPage("dashboard")}
                />
                <NavButton
                  label="Order Flow"
                  shortcut="2"
                  active={page === "orderflow"}
                  onClick={() => setPage("orderflow")}
                />
                <NavButton
                  label="Backtest"
                  shortcut="3"
                  active={page === "backtest"}
                  onClick={() => setPage("backtest")}
                />
                <NavButton
                  label="AI Agent"
                  shortcut="4"
                  active={page === "agent"}
                  onClick={() => setPage("agent")}
                />
                <NavButton
                  label="Settings"
                  shortcut="5"
                  active={page === "settings"}
                  onClick={() => setPage("settings")}
                />
              </div>
            </div>
          </nav>

          {/* Content */}
          <main className="mx-auto max-w-7xl p-6">
            <ErrorBoundary>
              {page === "dashboard" && <Dashboard />}
              {page === "orderflow" && <FootprintChart />}
              {page === "backtest" && <BacktestPage />}
              {page === "agent" && <AgentPanel />}
              {page === "settings" && <SettingsPage />}
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
