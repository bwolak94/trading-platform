import { useCallback, useId, useMemo, useState } from "react";

// --- Types ---

type TradeDirection = "LONG" | "SHORT";

interface TradeEntry {
  id: string;
  asset: string;
  direction: TradeDirection;
  entryPrice: number;
  exitPrice: number;
  size: number;
  date: string;
  notes: string;
  tags: string[];
  createdAt: number;
}

interface TradeFormState {
  asset: string;
  direction: TradeDirection;
  entryPrice: string;
  exitPrice: string;
  size: string;
  date: string;
  notes: string;
  tagsInput: string;
}

// --- localStorage helpers ---

const STORAGE_KEY = "trade-journal-entries";

function loadTrades(): TradeEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as TradeEntry[];
  } catch {
    return [];
  }
}

function saveTrades(trades: TradeEntry[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(trades));
}

// --- PnL calculation ---

function calculatePnl(trade: TradeEntry): number {
  const diff = trade.direction === "LONG"
    ? trade.exitPrice - trade.entryPrice
    : trade.entryPrice - trade.exitPrice;
  return diff * trade.size;
}

function calculatePnlPct(trade: TradeEntry): number {
  if (trade.entryPrice === 0) return 0;
  const diff = trade.direction === "LONG"
    ? (trade.exitPrice - trade.entryPrice) / trade.entryPrice
    : (trade.entryPrice - trade.exitPrice) / trade.entryPrice;
  return diff * 100;
}

// --- Default form state ---

function defaultFormState(): TradeFormState {
  return {
    asset: "BTCUSDT",
    direction: "LONG",
    entryPrice: "",
    exitPrice: "",
    size: "",
    date: new Date().toISOString().slice(0, 10),
    notes: "",
    tagsInput: "",
  };
}

// --- Component ---

export function TradeJournal() {
  const [trades, setTrades] = useState<TradeEntry[]>(loadTrades);
  const [form, setForm] = useState<TradeFormState>(defaultFormState);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const formId = useId();

  const updateTrades = useCallback((next: TradeEntry[]) => {
    setTrades(next);
    saveTrades(next);
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();

      const entryPrice = parseFloat(form.entryPrice);
      const exitPrice = parseFloat(form.exitPrice);
      const size = parseFloat(form.size);

      if (!form.asset.trim() || isNaN(entryPrice) || isNaN(exitPrice) || isNaN(size)) {
        return;
      }

      const tags = form.tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const newTrade: TradeEntry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        asset: form.asset.trim().toUpperCase(),
        direction: form.direction,
        entryPrice,
        exitPrice,
        size,
        date: form.date,
        notes: form.notes.trim(),
        tags,
        createdAt: Date.now(),
      };

      updateTrades([newTrade, ...trades]);
      setForm(defaultFormState());
      setIsFormOpen(false);
    },
    [form, trades, updateTrades],
  );

  const handleDelete = useCallback(
    (id: string) => {
      updateTrades(trades.filter((t) => t.id !== id));
    },
    [trades, updateTrades],
  );

  const handleFieldChange = useCallback(
    (field: keyof TradeFormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
    },
    [],
  );

  // --- Summary stats ---
  const stats = useMemo(() => {
    if (trades.length === 0) {
      return { total: 0, wins: 0, winRate: 0, avgPnl: 0, best: 0, worst: 0 };
    }

    const pnls = trades.map(calculatePnl);
    const wins = pnls.filter((p) => p > 0).length;

    return {
      total: trades.length,
      wins,
      winRate: (wins / trades.length) * 100,
      avgPnl: pnls.reduce((a, b) => a + b, 0) / pnls.length,
      best: Math.max(...pnls),
      worst: Math.min(...pnls),
    };
  }, [trades]);

  return (
    <div
      className="rounded-lg border border-border bg-surface p-4"
      aria-label="Trade journal"
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Trade Journal</h3>
        <button
          type="button"
          onClick={() => { setIsFormOpen((o) => !o); }}
          className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-blue-500"
          aria-expanded={isFormOpen}
          aria-controls={`${formId}-form`}
        >
          {isFormOpen ? "Cancel" : "+ New Trade"}
        </button>
      </div>

      {/* Summary Stats */}
      {trades.length > 0 && (
        <div className="mb-4 grid grid-cols-3 gap-2 sm:grid-cols-5" aria-label="Trade summary statistics">
          <StatBox label="Trades" value={stats.total.toString()} />
          <StatBox
            label="Win Rate"
            value={`${stats.winRate.toFixed(1)}%`}
            color={stats.winRate >= 50 ? "text-green-400" : "text-red-400"}
          />
          <StatBox
            label="Avg PnL"
            value={`$${stats.avgPnl.toFixed(2)}`}
            color={stats.avgPnl >= 0 ? "text-green-400" : "text-red-400"}
          />
          <StatBox
            label="Best"
            value={`$${stats.best.toFixed(2)}`}
            color="text-green-400"
          />
          <StatBox
            label="Worst"
            value={`$${stats.worst.toFixed(2)}`}
            color="text-red-400"
          />
        </div>
      )}

      {/* Form */}
      {isFormOpen && (
        <form
          id={`${formId}-form`}
          onSubmit={handleSubmit}
          className="mb-4 space-y-3 rounded-lg border border-border bg-background/50 p-3"
          aria-label="New trade entry form"
        >
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div>
              <label htmlFor={`${formId}-asset`} className="mb-1 block text-[10px] text-gray-500">
                Asset
              </label>
              <input
                id={`${formId}-asset`}
                type="text"
                value={form.asset}
                onChange={handleFieldChange("asset")}
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                placeholder="BTCUSDT"
                required
              />
            </div>
            <div>
              <label htmlFor={`${formId}-direction`} className="mb-1 block text-[10px] text-gray-500">
                Direction
              </label>
              <select
                id={`${formId}-direction`}
                value={form.direction}
                onChange={handleFieldChange("direction")}
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="LONG">LONG</option>
                <option value="SHORT">SHORT</option>
              </select>
            </div>
            <div>
              <label htmlFor={`${formId}-entry`} className="mb-1 block text-[10px] text-gray-500">
                Entry Price
              </label>
              <input
                id={`${formId}-entry`}
                type="number"
                step="any"
                value={form.entryPrice}
                onChange={handleFieldChange("entryPrice")}
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                placeholder="0.00"
                required
              />
            </div>
            <div>
              <label htmlFor={`${formId}-exit`} className="mb-1 block text-[10px] text-gray-500">
                Exit Price
              </label>
              <input
                id={`${formId}-exit`}
                type="number"
                step="any"
                value={form.exitPrice}
                onChange={handleFieldChange("exitPrice")}
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                placeholder="0.00"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <div>
              <label htmlFor={`${formId}-size`} className="mb-1 block text-[10px] text-gray-500">
                Size
              </label>
              <input
                id={`${formId}-size`}
                type="number"
                step="any"
                value={form.size}
                onChange={handleFieldChange("size")}
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                placeholder="0.01"
                required
              />
            </div>
            <div>
              <label htmlFor={`${formId}-date`} className="mb-1 block text-[10px] text-gray-500">
                Date
              </label>
              <input
                id={`${formId}-date`}
                type="date"
                value={form.date}
                onChange={handleFieldChange("date")}
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div className="col-span-2 sm:col-span-1">
              <label htmlFor={`${formId}-tags`} className="mb-1 block text-[10px] text-gray-500">
                Tags (comma-separated)
              </label>
              <input
                id={`${formId}-tags`}
                type="text"
                value={form.tagsInput}
                onChange={handleFieldChange("tagsInput")}
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
                placeholder="trend, scalp"
              />
            </div>
          </div>

          <div>
            <label htmlFor={`${formId}-notes`} className="mb-1 block text-[10px] text-gray-500">
              Notes
            </label>
            <textarea
              id={`${formId}-notes`}
              value={form.notes}
              onChange={handleFieldChange("notes")}
              rows={2}
              className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              placeholder="Trade rationale, lessons learned..."
            />
          </div>

          <button
            type="submit"
            className="w-full rounded bg-blue-600 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-500"
          >
            Save Trade
          </button>
        </form>
      )}

      {/* Trade List */}
      {trades.length === 0 ? (
        <div className="text-center text-sm text-gray-500">
          No trades recorded yet — click &quot;+ New Trade&quot; to add your first entry.
        </div>
      ) : (
        <div className="space-y-2" aria-label="Past trades list">
          {trades.map((trade) => {
            const pnl = calculatePnl(trade);
            const pnlPct = calculatePnlPct(trade);
            const isWin = pnl >= 0;

            return (
              <div
                key={trade.id}
                className={`rounded-lg border p-3 transition-colors ${
                  isWin
                    ? "border-green-900/40 bg-green-900/10"
                    : "border-red-900/40 bg-red-900/10"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-white">{trade.asset}</span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          trade.direction === "LONG"
                            ? "bg-green-900/30 text-green-400"
                            : "bg-red-900/30 text-red-400"
                        }`}
                      >
                        {trade.direction}
                      </span>
                      <span className="text-[10px] text-gray-500">{trade.date}</span>
                    </div>

                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[10px] text-gray-400">
                      <span>Entry: <span className="font-mono text-white">{trade.entryPrice}</span></span>
                      <span>Exit: <span className="font-mono text-white">{trade.exitPrice}</span></span>
                      <span>Size: <span className="font-mono text-white">{trade.size}</span></span>
                    </div>

                    {trade.tags.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {trade.tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded bg-purple-900/50 px-1.5 py-0.5 text-[10px] text-purple-300"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}

                    {trade.notes && (
                      <p className="mt-1 text-[10px] text-gray-500">{trade.notes}</p>
                    )}
                  </div>

                  <div className="flex flex-col items-end gap-1">
                    <span
                      className={`text-sm font-semibold font-mono ${
                        isWin ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
                    </span>
                    <span
                      className={`text-[10px] font-mono ${
                        isWin ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                    </span>
                    <button
                      type="button"
                      onClick={() => { handleDelete(trade.id); }}
                      className="mt-1 rounded px-1.5 py-0.5 text-[10px] text-gray-500 transition-colors hover:bg-red-900/30 hover:text-red-400"
                      aria-label={`Delete trade ${trade.asset} from ${trade.date}`}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --- Sub-components ---

interface StatBoxProps {
  label: string;
  value: string;
  color?: string;
}

function StatBox({ label, value, color = "text-white" }: StatBoxProps) {
  return (
    <div className="rounded border border-border bg-background/50 px-2 py-1.5 text-center">
      <div className="text-[10px] text-gray-500">{label}</div>
      <div className={`text-xs font-semibold font-mono ${color}`}>{value}</div>
    </div>
  );
}
