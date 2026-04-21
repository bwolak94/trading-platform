import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { runAnalysis, updatePositionNotes } from "../../api/client";
import type { AnalysisResult, SimulatedPosition } from "../../api/client";

// ------------------------------------------------------------------ //
// Types & constants                                                    //
// ------------------------------------------------------------------ //

interface Props {
  position: SimulatedPosition | null;
  onClose: () => void;
  onNavigateToChart: (symbol: string) => void;
}

const QUICK_TAGS = [
  "setups",
  "winner",
  "loser",
  "fomo",
  "revenge",
  "system",
  "breakout",
  "reversal",
] as const;

const TAG_COLORS: Record<string, string> = {
  winner: "bg-green-500/20 text-green-400 border-green-500/30",
  loser: "bg-red-500/20 text-red-400 border-red-500/30",
  fomo: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  revenge: "bg-red-600/20 text-red-300 border-red-600/30",
  system: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  setups: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  breakout: "bg-teal-500/20 text-teal-400 border-teal-500/30",
  reversal: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
};

const DEFAULT_TAG_COLOR = "bg-zinc-700/50 text-zinc-300 border-zinc-600/40";

const CHECKLIST_ITEMS = [
  { id: "regime", label: "Regime confirmed (not counter-trend)" },
  { id: "correlation", label: "No high-correlation positions open" },
  { id: "risk", label: "Position size within daily risk limit" },
  { id: "sl_placed", label: "Stop-loss level identified" },
  { id: "r_ratio", label: "R:R ratio \u2265 1.5:1" },
] as const;

type ChecklistItemId = (typeof CHECKLIST_ITEMS)[number]["id"];

// ------------------------------------------------------------------ //
// Helpers                                                             //
// ------------------------------------------------------------------ //

function pctDiff(
  target: number,
  entry: number,
  direction: "LONG" | "SHORT",
): number {
  if (direction === "LONG") return ((target - entry) / entry) * 100;
  return ((entry - target) / entry) * 100;
}

// ------------------------------------------------------------------ //
// LevelRow                                                            //
// ------------------------------------------------------------------ //

function LevelRow({
  label,
  price,
  variant,
  isCurrent,
  pctFromEntry,
}: {
  label: string;
  price: number;
  variant: "entry" | "sl" | "tp";
  isCurrent?: boolean;
  pctFromEntry?: number;
}) {
  const colorMap = {
    entry: "border-blue-500/40 bg-blue-500/10 text-blue-300",
    sl: "border-red-500/40 bg-red-500/10 text-red-300",
    tp: "border-green-500/40 bg-green-500/10 text-green-300",
  };

  return (
    <div
      className={`flex items-center justify-between rounded-md border px-3 py-2 ${colorMap[variant]} ${isCurrent ? "ring-1 ring-white/20" : ""}`}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider">
          {label}
        </span>
        {isCurrent && (
          <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] text-white/60">
            current
          </span>
        )}
      </div>
      <div className="text-right">
        <span className="font-mono font-semibold">
          {price.toFixed(6).replace(/\.?0+$/, "")}
        </span>
        {pctFromEntry !== undefined && (
          <span
            className={`ml-2 text-xs ${pctFromEntry >= 0 ? "text-green-400" : "text-red-400"}`}
          >
            {pctFromEntry >= 0 ? "+" : ""}
            {pctFromEntry.toFixed(2)}%
          </span>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
// MAE / MFE tooltip                                                   //
// ------------------------------------------------------------------ //

function MaeMfeTooltip() {
  const [visible, setVisible] = useState(false);

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label="What are MAE and MFE?"
        className="ml-1 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-zinc-600 text-[9px] text-zinc-500 hover:border-zinc-400 hover:text-zinc-300"
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onFocus={() => setVisible(true)}
        onBlur={() => setVisible(false)}
      >
        ?
      </button>
      {visible && (
        <span
          role="tooltip"
          className="absolute bottom-5 left-0 z-50 w-56 rounded-md border border-border bg-zinc-900 px-2.5 py-2 text-[11px] leading-relaxed text-zinc-300 shadow-xl"
        >
          <strong>MAE</strong> (Max Adverse Excursion): the worst unrealised
          loss during the trade.
          <br />
          <strong>MFE</strong> (Max Favorable Excursion): the best unrealised
          gain during the trade.
        </span>
      )}
    </span>
  );
}

// ------------------------------------------------------------------ //
// Pre-Trade Checklist (Feature 63)                                    //
// ------------------------------------------------------------------ //

function PreTradeChecklist() {
  const [checked, setChecked] = useState<Record<ChecklistItemId, boolean>>(
    () =>
      Object.fromEntries(
        CHECKLIST_ITEMS.map((item) => [item.id, false]),
      ) as Record<ChecklistItemId, boolean>,
  );
  const [expanded, setExpanded] = useState(true);

  const checkedCount = Object.values(checked).filter(Boolean).length;
  const total = CHECKLIST_ITEMS.length;
  const readinessPct = (checkedCount / total) * 100;
  const isReady = checkedCount === total;

  const toggle = useCallback((id: ChecklistItemId) => {
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  return (
    <section aria-labelledby="checklist-heading">
      <button
        id="checklist-heading"
        type="button"
        onClick={() => setExpanded((p) => !p)}
        className="flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
        aria-expanded={expanded}
        aria-controls="checklist-body"
      >
        <span>Pre-Trade Checklist</span>
        <span aria-hidden="true">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div id="checklist-body" className="mt-2 flex flex-col gap-2">
          {/* Readiness progress */}
          <div className="flex items-center gap-3">
            <div
              className="flex-1 h-1.5 overflow-hidden rounded-full bg-border/50"
              role="progressbar"
              aria-valuenow={checkedCount}
              aria-valuemin={0}
              aria-valuemax={total}
              aria-label={`Readiness: ${checkedCount} of ${total}`}
            >
              <div
                className={`h-full rounded-full transition-all duration-300 ${isReady ? "bg-green-400" : "bg-amber-400"}`}
                style={{ width: `${readinessPct}%` }}
              />
            </div>
            <span className="text-xs font-semibold text-muted-foreground whitespace-nowrap">
              Readiness: {checkedCount}/{total}
            </span>
          </div>

          {isReady && (
            <div className="flex items-center gap-1.5 rounded-md border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm font-semibold text-green-400">
              <span aria-hidden="true">&#10003;</span>
              <span>Ready to Trade</span>
            </div>
          )}

          {CHECKLIST_ITEMS.map((item) => (
            <label
              key={item.id}
              className="flex cursor-pointer items-start gap-2.5 rounded-md border border-border/40 bg-surface/30 px-3 py-2 hover:bg-surface/60"
            >
              <input
                type="checkbox"
                checked={checked[item.id]}
                onChange={() => toggle(item.id)}
                className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 accent-green-500"
                aria-label={item.label}
              />
              <span className="text-xs text-foreground">{item.label}</span>
            </label>
          ))}
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ //
// Trade Journal — Tags + Notes (Feature 45)                          //
// ------------------------------------------------------------------ //

interface TradeJournalProps {
  positionId: string;
  initialTags: string[];
  initialNotes: string;
}

function TradeJournal({
  positionId,
  initialTags,
  initialNotes,
}: TradeJournalProps) {
  const queryClient = useQueryClient();
  const [tags, setTags] = useState<string[]>(initialTags);
  const [notes, setNotes] = useState(initialNotes);
  const [tagInput, setTagInput] = useState("");
  const tagInputRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: (data: { tags?: string[]; notes?: string }) =>
      updatePositionNotes(Number(positionId), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["closed-positions"] });
    },
  });

  const saveNotes = useCallback(
    (value: string) => {
      mutation.mutate({ notes: value });
    },
    [mutation],
  );

  const saveTags = useCallback(
    (newTags: string[]) => {
      mutation.mutate({ tags: newTags });
    },
    [mutation],
  );

  const addTag = useCallback(
    (tag: string) => {
      const trimmed = tag.trim().toLowerCase();
      if (!trimmed || tags.includes(trimmed)) return;
      const next = [...tags, trimmed];
      setTags(next);
      saveTags(next);
    },
    [tags, saveTags],
  );

  const removeTag = useCallback(
    (tag: string) => {
      const next = tags.filter((t) => t !== tag);
      setTags(next);
      saveTags(next);
    },
    [tags, saveTags],
  );

  const handleTagInputKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        addTag(tagInput);
        setTagInput("");
      } else if (e.key === "Backspace" && !tagInput && tags.length > 0) {
        removeTag(tags[tags.length - 1]);
      }
    },
    [tagInput, tags, addTag, removeTag],
  );

  return (
    <section aria-labelledby="journal-heading" className="flex flex-col gap-3">
      <h3
        id="journal-heading"
        className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
      >
        Trade Journal
      </h3>

      {/* Tags */}
      <div>
        <p className="mb-1.5 text-xs text-muted-foreground">Tags</p>

        {/* Quick tags */}
        <div className="mb-2 flex flex-wrap gap-1">
          {QUICK_TAGS.map((qt) => {
            const active = tags.includes(qt);
            return (
              <button
                key={qt}
                type="button"
                onClick={() => (active ? removeTag(qt) : addTag(qt))}
                className={`rounded-full border px-2 py-0.5 text-[11px] font-medium transition-opacity ${
                  active
                    ? (TAG_COLORS[qt] ?? DEFAULT_TAG_COLOR)
                    : "border-border/40 bg-surface/30 text-muted-foreground opacity-60 hover:opacity-100"
                }`}
                aria-pressed={active}
                aria-label={`${active ? "Remove" : "Add"} tag: ${qt}`}
              >
                {qt}
              </button>
            );
          })}
        </div>

        {/* Current tags */}
        <div
          className="flex min-h-[36px] flex-wrap items-center gap-1.5 rounded-md border border-border/50 bg-surface/30 px-2 py-1.5"
          onClick={() => tagInputRef.current?.focus()}
          role="group"
          aria-label="Active tags"
        >
          {tags.map((tag) => (
            <span
              key={tag}
              className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${(TAG_COLORS[tag] ?? DEFAULT_TAG_COLOR)}`}
            >
              {tag}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeTag(tag);
                }}
                className="ml-0.5 rounded-full hover:opacity-70"
                aria-label={`Remove tag ${tag}`}
              >
                &times;
              </button>
            </span>
          ))}
          <input
            ref={tagInputRef}
            type="text"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={handleTagInputKeyDown}
            onBlur={() => {
              if (tagInput.trim()) {
                addTag(tagInput);
                setTagInput("");
              }
            }}
            placeholder={tags.length === 0 ? "Add tag…" : ""}
            className="min-w-[60px] flex-1 bg-transparent text-[11px] text-foreground outline-none placeholder:text-muted-foreground/60"
            aria-label="Add new tag"
          />
        </div>
      </div>

      {/* Notes */}
      <div>
        <p className="mb-1.5 text-xs text-muted-foreground">Notes</p>
        <textarea
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={(e) => saveNotes(e.target.value)}
          placeholder="Add trade notes, observations..."
          className="w-full resize-none rounded-md border border-border/50 bg-surface/30 px-3 py-2 text-xs text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-accent/60 focus:ring-1 focus:ring-accent/30"
          aria-label="Trade notes"
        />
        {mutation.isPending && (
          <p className="mt-0.5 text-[10px] text-muted-foreground">Saving…</p>
        )}
        {mutation.isError && (
          <p className="mt-0.5 text-[10px] text-red-400">Save failed</p>
        )}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ //
// AI Analysis section                                                 //
// ------------------------------------------------------------------ //

function AnalysisSection({
  analysis,
}: {
  analysis: AnalysisResult | undefined;
}) {
  if (!analysis) {
    return (
      <div className="flex h-16 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
        Loading AI analysis…
      </div>
    );
  }

  const regime = analysis.regime;
  const regimeColor: Record<string, string> = {
    TRENDING_BULL: "text-green-400",
    TRENDING_BEAR: "text-red-400",
    CONSOLIDATION: "text-yellow-400",
    HIGH_VOLATILITY: "text-orange-400",
    RANGING: "text-blue-400",
  };

  const bestSignal = analysis.strategies
    .filter((s) => s.signal !== null)
    .sort((a, b) => (b.signal?.confidence ?? 0) - (a.signal?.confidence ?? 0))[0];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between rounded-md border border-border/50 bg-surface/50 px-3 py-2">
        <span className="text-xs text-muted-foreground">Market Regime</span>
        <span
          className={`text-sm font-semibold ${regimeColor[regime.regime] ?? "text-foreground"}`}
        >
          {regime.regime.replace(/_/g, " ")}
          <span className="ml-1 text-xs font-normal text-muted-foreground">
            {(regime.confidence * 100).toFixed(0)}% conf
          </span>
        </span>
      </div>

      <div className="flex flex-col gap-1.5">
        {analysis.strategies.map((s) => (
          <div
            key={s.name}
            className={`flex items-center justify-between rounded-md border px-3 py-2 text-xs ${
              s.compatible_with_regime
                ? "border-green-500/20 bg-green-500/5"
                : "border-border/50 bg-surface/30 opacity-60"
            }`}
          >
            <div className="flex items-center gap-2">
              <span
                className={`h-1.5 w-1.5 rounded-full ${s.compatible_with_regime ? "bg-green-400" : "bg-zinc-600"}`}
              />
              <span className="font-medium text-foreground">
                {s.name.replace(/_/g, " ")}
              </span>
            </div>
            {s.signal ? (
              <div className="flex items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 font-semibold ${
                    s.signal.direction === "LONG"
                      ? "bg-green-500/20 text-green-400"
                      : "bg-red-500/20 text-red-400"
                  }`}
                >
                  {s.signal.direction}
                </span>
                <span className="text-muted-foreground">
                  {s.signal.confidence}%
                </span>
              </div>
            ) : (
              <span className="text-muted-foreground">No signal</span>
            )}
          </div>
        ))}
      </div>

      {bestSignal?.signal?.factors && bestSignal.signal.factors.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            Key Factors
          </span>
          {bestSignal.signal.factors.slice(0, 4).map((f, i) => (
            <div key={i} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{f.name}</span>
              <span
                className={`font-medium ${
                  f.label === "BULLISH" || f.label === "POSITIVE"
                    ? "text-green-400"
                    : f.label === "BEARISH" || f.label === "NEGATIVE"
                      ? "text-red-400"
                      : "text-muted-foreground"
                }`}
              >
                {f.label}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ //
// Drawer                                                              //
// ------------------------------------------------------------------ //

export function PositionDetailDrawer({
  position,
  onClose,
  onNavigateToChart,
}: Props) {
  // Close on Escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Lock body scroll when drawer is open
  useEffect(() => {
    if (position) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [position]);

  const analysisSymbol = position?.symbol.replace("/", "") ?? "";
  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ["position-analysis", analysisSymbol],
    queryFn: () => runAnalysis(analysisSymbol, "1h"),
    enabled: !!position,
    staleTime: 60_000,
  });

  if (!position) return null;

  const isLong = position.direction === "LONG";
  const dirColor = isLong ? "text-green-400" : "text-red-400";
  const pnlPositive = position.pnl_pct >= 0;

  const riskPct = pctDiff(
    position.stop_loss,
    position.entry_price,
    position.direction,
  );
  const tp1Pct = pctDiff(
    position.take_profit_1,
    position.entry_price,
    position.direction,
  );
  const tp2Pct =
    position.take_profit_2 != null
      ? pctDiff(position.take_profit_2, position.entry_price, position.direction)
      : null;
  const tp3Pct =
    position.take_profit_3 != null
      ? pctDiff(position.take_profit_3, position.entry_price, position.direction)
      : null;
  const rr = tp1Pct / Math.abs(riskPct);

  const durationMs = Date.now() - new Date(position.opened_at).getTime();
  const durationMin = Math.floor(durationMs / 60_000);
  const durationStr =
    durationMin < 60
      ? `${durationMin}m`
      : `${Math.floor(durationMin / 60)}h ${durationMin % 60}m`;

  const isClosed = position.status !== "OPEN";

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-border bg-background shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label={`Position details for ${position.symbol}`}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background px-5 py-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-foreground">
                {position.symbol}
              </span>
              <span className={`text-sm font-semibold ${dirColor}`}>
                {isLong ? "▲" : "▼"} {position.direction}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {position.strategy.replace(/_/g, " ")} · {position.regime} ·{" "}
              {position.confidence}% conf
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-2 text-muted-foreground hover:bg-surface hover:text-foreground"
            aria-label="Close drawer"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <div className="flex flex-col gap-5 p-5">
          {/* Pre-Trade Checklist — only for open positions */}
          {!isClosed && <PreTradeChecklist />}

          {/* PnL banner */}
          <div
            className={`flex items-center justify-between rounded-lg border px-4 py-3 ${
              pnlPositive
                ? "border-green-500/30 bg-green-500/10"
                : "border-red-500/30 bg-red-500/10"
            }`}
          >
            <div>
              <p className="text-xs text-muted-foreground">
                {isClosed ? "Closed PnL" : "Running PnL"}
              </p>
              <p
                className={`text-2xl font-bold ${pnlPositive ? "text-green-400" : "text-red-400"}`}
              >
                {pnlPositive ? "+" : ""}
                {position.pnl_pct.toFixed(2)}%
              </p>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <p>{isClosed ? "Held" : "Open"} {durationStr}</p>
              <p>{position.status}</p>
              {position.exit_reason && (
                <p className="text-zinc-500">{position.exit_reason}</p>
              )}
            </div>
          </div>

          {/* MAE / MFE metrics */}
          {(position.mae_pct != null || position.mfe_pct != null) && (
            <div className="grid grid-cols-2 gap-2">
              {position.mae_pct != null && (
                <div className="rounded-md border border-red-500/20 bg-red-500/5 p-2 text-center">
                  <div className="flex items-center justify-center gap-0.5 text-[10px] text-muted-foreground">
                    Max Adverse
                    <MaeMfeTooltip />
                  </div>
                  <p className="font-mono text-sm font-semibold text-red-400">
                    -{Math.abs(position.mae_pct).toFixed(2)}%
                  </p>
                </div>
              )}
              {position.mfe_pct != null && (
                <div className="rounded-md border border-green-500/20 bg-green-500/5 p-2 text-center">
                  <div className="flex items-center justify-center gap-0.5 text-[10px] text-muted-foreground">
                    Max Favorable
                    <MaeMfeTooltip />
                  </div>
                  <p className="font-mono text-sm font-semibold text-green-400">
                    +{position.mfe_pct.toFixed(2)}%
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Price levels */}
          <section aria-labelledby="levels-heading">
            <h3
              id="levels-heading"
              className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
            >
              Price Levels
            </h3>
            <div className="flex flex-col gap-1.5">
              {position.take_profit_3 != null && tp3Pct != null && (
                <LevelRow
                  label="TP3"
                  price={position.take_profit_3}
                  variant="tp"
                  pctFromEntry={tp3Pct}
                />
              )}
              {position.take_profit_2 != null && tp2Pct != null && (
                <LevelRow
                  label="TP2"
                  price={position.take_profit_2}
                  variant="tp"
                  pctFromEntry={tp2Pct}
                />
              )}
              <LevelRow
                label="TP1"
                price={position.take_profit_1}
                variant="tp"
                pctFromEntry={tp1Pct}
              />
              <LevelRow
                label="Entry"
                price={position.entry_price}
                variant="entry"
                isCurrent={position.status === "OPEN"}
              />
              <LevelRow
                label="Stop Loss"
                price={position.stop_loss}
                variant="sl"
                pctFromEntry={riskPct}
              />
            </div>
          </section>

          {/* R:R summary */}
          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded-md border border-border/50 bg-surface/50 p-2">
              <p className="text-muted-foreground">Risk</p>
              <p className="font-semibold text-red-400">
                {Math.abs(riskPct).toFixed(2)}%
              </p>
            </div>
            <div className="rounded-md border border-border/50 bg-surface/50 p-2">
              <p className="text-muted-foreground">Reward (TP1)</p>
              <p className="font-semibold text-green-400">
                +{tp1Pct.toFixed(2)}%
              </p>
            </div>
            <div className="rounded-md border border-border/50 bg-surface/50 p-2">
              <p className="text-muted-foreground">R:R</p>
              <p
                className={`font-bold ${rr >= 2 ? "text-green-400" : rr >= 1 ? "text-yellow-400" : "text-red-400"}`}
              >
                1:{rr.toFixed(1)}
              </p>
            </div>
          </div>

          {/* View on chart */}
          <button
            onClick={() => {
              onNavigateToChart(position.symbol.replace("/", ""));
              onClose();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-accent bg-accent/10 py-2.5 text-sm font-medium text-accent transition-colors hover:bg-accent/20"
            aria-label={`Navigate chart to ${position.symbol}`}
          >
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
            View on Chart
          </button>

          {/* Trade Journal — only for closed positions */}
          {isClosed && (
            <TradeJournal
              positionId={position.id}
              initialTags={position.tags ?? []}
              initialNotes={position.notes ?? ""}
            />
          )}

          {/* AI Technical Analysis */}
          <section aria-labelledby="analysis-heading">
            <h3
              id="analysis-heading"
              className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
            >
              AI Technical Analysis
            </h3>
            {analysisLoading ? (
              <div className="flex h-16 items-center justify-center text-sm text-muted-foreground">
                Running analysis…
              </div>
            ) : (
              <AnalysisSection analysis={analysis} />
            )}
          </section>
        </div>
      </aside>
    </>
  );
}
