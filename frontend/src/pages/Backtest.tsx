import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchBacktestResults,
  runBacktest,
} from "../api/client";
import type { BacktestRequest, BacktestResult } from "../types";
import { backtestFormSchema } from "../lib/validation";

const STRATEGIES = [
  { value: "trend_following", label: "Trend Following" },
  { value: "mean_reversion", label: "Mean Reversion" },
  { value: "smc", label: "SMC (Smart Money)" },
  { value: "volume_breakout", label: "Volume Breakout" },
];

const ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
const TIMEFRAMES = ["1h", "4h", "1D"];

export function BacktestPage() {
  const [form, setForm] = useState<BacktestRequest>({
    strategy: "trend_following",
    asset: "BTC/USDT",
    timeframe: "4h",
    from_date: "2023-01-01",
    to_date: "2025-01-01",
    initial_capital: 10000,
    risk_per_trade_pct: 1.5,
  });

  const [selectedResult, setSelectedResult] = useState<BacktestResult | null>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  const resultsQuery = useQuery({
    queryKey: ["backtestResults"],
    queryFn: fetchBacktestResults,
  });

  const runMutation = useMutation({
    mutationFn: runBacktest,
    onSuccess: () => {
      void resultsQuery.refetch();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setValidationErrors({});

    const result = backtestFormSchema.safeParse({
      strategy: form.strategy,
      asset: form.asset,
      timeframe: form.timeframe,
      start_date: form.from_date,
      end_date: form.to_date,
      initial_capital: form.initial_capital,
      risk_per_trade_pct: form.risk_per_trade_pct,
    });

    if (!result.success) {
      const errors: Record<string, string> = {};
      for (const issue of result.error.issues) {
        const key = issue.path.join(".");
        if (!errors[key]) {
          errors[key] = issue.message;
        }
      }
      setValidationErrors(errors);
      return;
    }

    runMutation.mutate(form);
  };

  const updateField = <K extends keyof BacktestRequest>(
    key: K,
    value: BacktestRequest[K],
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Backtesting</h1>

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        className="grid grid-cols-2 gap-4 rounded-lg border border-border bg-surface p-5 lg:grid-cols-4"
      >
        <SelectField
          label="Strategy"
          value={form.strategy}
          options={STRATEGIES}
          onChange={(v) => { updateField("strategy", v); }}
        />
        <SelectField
          label="Asset"
          value={form.asset}
          options={ASSETS.map((a) => ({ value: a, label: a }))}
          onChange={(v) => { updateField("asset", v); }}
        />
        <SelectField
          label="Timeframe"
          value={form.timeframe}
          options={TIMEFRAMES.map((t) => ({ value: t, label: t }))}
          onChange={(v) => { updateField("timeframe", v); }}
        />
        <InputField
          label="Capital ($)"
          type="number"
          value={form.initial_capital}
          onChange={(v) => { updateField("initial_capital", Number(v)); }}
        />
        <InputField
          label="From"
          type="date"
          value={form.from_date}
          onChange={(v) => { updateField("from_date", v); }}
        />
        <InputField
          label="To"
          type="date"
          value={form.to_date}
          onChange={(v) => { updateField("to_date", v); }}
        />
        <InputField
          label="Risk %"
          type="number"
          value={form.risk_per_trade_pct}
          onChange={(v) => { updateField("risk_per_trade_pct", Number(v)); }}
        />
        <div className="flex items-end">
          <button
            type="submit"
            disabled={runMutation.isPending}
            className="w-full rounded bg-bullish px-4 py-2 text-sm font-medium text-background hover:bg-bullish/80 disabled:opacity-50"
            aria-label="Run backtest"
          >
            {runMutation.isPending ? "Running..." : "Run Backtest"}
          </button>
        </div>
      </form>

      {Object.keys(validationErrors).length > 0 && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/10 p-4">
          <p className="mb-1 text-sm font-medium text-bearish">Validation errors:</p>
          <ul className="list-inside list-disc text-sm text-bearish/80">
            {Object.entries(validationErrors).map(([field, message]) => (
              <li key={field}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      {runMutation.isSuccess && (
        <p className="text-sm text-bullish">
          Backtest queued (task: {runMutation.data.task_id})
        </p>
      )}

      {/* Results table */}
      <div className="rounded-lg border border-border bg-surface">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">
            Results
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-xs text-gray-500">
              <tr>
                <th className="px-4 py-2">Strategy</th>
                <th className="px-4 py-2">Asset</th>
                <th className="px-4 py-2">TF</th>
                <th className="px-4 py-2">Trades</th>
                <th className="px-4 py-2">Win Rate</th>
                <th className="px-4 py-2">PF</th>
                <th className="px-4 py-2">Max DD</th>
                <th className="px-4 py-2">Sharpe</th>
                <th className="px-4 py-2">P(Ruin 20%)</th>
              </tr>
            </thead>
            <tbody>
              {(resultsQuery.data ?? []).map((r: BacktestResult) => (
                <tr
                  key={r.id}
                  onClick={() => { setSelectedResult(r); }}
                  className="cursor-pointer border-b border-border hover:bg-background"
                >
                  <td className="px-4 py-2 text-white">{r.strategy_name}</td>
                  <td className="px-4 py-2 font-mono">{r.asset}</td>
                  <td className="px-4 py-2">{r.timeframe}</td>
                  <td className="px-4 py-2 font-mono">{r.total_trades ?? "-"}</td>
                  <td className="px-4 py-2 font-mono">
                    {r.win_rate != null ? `${r.win_rate}%` : "-"}
                  </td>
                  <td className="px-4 py-2 font-mono">
                    {r.profit_factor?.toFixed(2) ?? "-"}
                  </td>
                  <td className="px-4 py-2 font-mono text-bearish">
                    {r.max_drawdown != null ? `${r.max_drawdown}%` : "-"}
                  </td>
                  <td className="px-4 py-2 font-mono">
                    {r.sharpe_ratio?.toFixed(2) ?? "-"}
                  </td>
                  <td className="px-4 py-2 font-mono">
                    {r.prob_ruin_20pct != null ? `${r.prob_ruin_20pct}%` : "-"}
                  </td>
                </tr>
              ))}
              {(resultsQuery.data ?? []).length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                    No backtest results yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Equity Curve Chart */}
      {selectedResult?.equity_curve && selectedResult.equity_curve.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-gray-500">
            Equity Curve — {selectedResult.strategy_name} ({selectedResult.asset})
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={selectedResult.equity_curve}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="date" stroke="#8b949e" tick={{ fontSize: 11 }} />
              <YAxis stroke="#8b949e" tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#161b22",
                  border: "1px solid #30363d",
                  borderRadius: "6px",
                }}
              />
              <Line
                type="monotone"
                dataKey="equity"
                stroke="#00d4aa"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="mt-3 text-right">
            <button
              onClick={() => { exportCSV(selectedResult); }}
              type="button"
              className="rounded border border-border px-3 py-1 text-xs text-gray-400 hover:bg-background"
              aria-label="Export results as CSV"
            >
              Export CSV
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Helpers ---

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-gray-500">{label}</label>
      <select
        value={value}
        onChange={(e) => { onChange(e.target.value); }}
        className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-white"
        aria-label={label}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function InputField({
  label,
  type,
  value,
  onChange,
}: {
  label: string;
  type: string;
  value: string | number;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-gray-500">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => { onChange(e.target.value); }}
        className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-white"
        aria-label={label}
      />
    </div>
  );
}

function exportCSV(result: BacktestResult) {
  if (!result.equity_curve) return;

  const header = "date,equity\n";
  const rows = result.equity_curve
    .map((p) => `${p.date},${p.equity}`)
    .join("\n");

  const blob = new Blob([header + rows], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `backtest_${result.strategy_name}_${result.asset}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
