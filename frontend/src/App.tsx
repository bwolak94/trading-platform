import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { BacktestPage } from "./pages/Backtest";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
    },
  },
});

type Page = "dashboard" | "backtest";

function App() {
  const [page, setPage] = useState<Page>("dashboard");

  return (
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
                active={page === "dashboard"}
                onClick={() => setPage("dashboard")}
              />
              <NavButton
                label="Backtest"
                active={page === "backtest"}
                onClick={() => setPage("backtest")}
              />
            </div>
          </div>
        </nav>

        {/* Content */}
        <main className="mx-auto max-w-7xl p-6">
          {page === "dashboard" && <Dashboard />}
          {page === "backtest" && <BacktestPage />}
        </main>
      </div>
    </QueryClientProvider>
  );
}

function NavButton({
  label,
  active,
  onClick,
}: {
  label: string;
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
      aria-label={`Navigate to ${label}`}
    >
      {label}
    </button>
  );
}

export default App;
