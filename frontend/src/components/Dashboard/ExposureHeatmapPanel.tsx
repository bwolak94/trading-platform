import { useQuery } from "@tanstack/react-query";
import { fetchOpenPositions } from "../../api/client";

/* ── Sector definitions ──────────────────────────────────────────────── */

interface SectorDefinition {
  name: string;
  symbols: readonly string[];
}

const SECTORS: readonly SectorDefinition[] = [
  { name: "Layer 1", symbols: ["BTC", "ETH", "SOL", "ADA", "AVAX", "DOT", "ATOM"] },
  { name: "Layer 2", symbols: ["MATIC", "POL", "ARB", "OP"] },
  { name: "DeFi", symbols: ["UNI", "AAVE", "LINK", "SUSHI", "CRV"] },
  { name: "Gaming / NFT", symbols: ["AXS", "SAND", "MANA"] },
  { name: "Exchange", symbols: ["BNB", "OKB"] },
  { name: "Meme", symbols: ["DOGE", "SHIB"] },
] as const;

/** Extract the base symbol from a trading pair such as "BTCUSDT" → "BTC". */
function extractBase(tradingPair: string): string {
  // Strip common quote currencies from the end, longest first to avoid greedy errors
  const quotes = ["USDT", "BUSD", "USDC", "BTC", "ETH", "BNB", "USD"];
  const upper = tradingPair.toUpperCase();
  for (const q of quotes) {
    if (upper.endsWith(q) && upper.length > q.length) {
      return upper.slice(0, upper.length - q.length);
    }
  }
  return upper;
}

function resolveSector(base: string): string {
  for (const sector of SECTORS) {
    if ((sector.symbols).includes(base)) {
      return sector.name;
    }
  }
  return "Other";
}

/* ── Colour helpers ──────────────────────────────────────────────────── */

interface ConcentrationBadge {
  label: string;
  cardClass: string;
  badgeClass: string;
}

function getConcentration(count: number): ConcentrationBadge {
  if (count === 0) {
    return {
      label: "None",
      cardClass: "border-border bg-surface",
      badgeClass: "bg-gray-700 text-gray-400",
    };
  }
  if (count <= 2) {
    return {
      label: "Balanced",
      cardClass: "border-bullish/30 bg-bullish/5",
      badgeClass: "bg-bullish/20 text-bullish",
    };
  }
  if (count <= 4) {
    return {
      label: "Moderate",
      cardClass: "border-yellow-500/30 bg-yellow-500/5",
      badgeClass: "bg-yellow-500/20 text-yellow-400",
    };
  }
  return {
    label: "Concentrated",
    cardClass: "border-bearish/30 bg-bearish/5",
    badgeClass: "bg-bearish/20 text-bearish",
  };
}

/* ── Types ───────────────────────────────────────────────────────────── */

interface SectorSummary {
  name: string;
  count: number;
  symbols: string[];
}

/* ── Component ───────────────────────────────────────────────────────── */

export function ExposureHeatmapPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["openPositions"],
    queryFn: fetchOpenPositions,
    refetchInterval: 15_000,
  });

  // Build sector summaries from open positions
  const sectorMap = new Map<string, SectorSummary>();

  // Pre-populate all known sectors so they always render
  for (const sector of SECTORS) {
    sectorMap.set(sector.name, { name: sector.name, count: 0, symbols: [] });
  }
  sectorMap.set("Other", { name: "Other", count: 0, symbols: [] });

  if (data?.positions) {
    for (const pos of data.positions) {
      const base = extractBase(pos.symbol);
      const sector = resolveSector(base);
      const existing = sectorMap.get(sector);
      if (existing) {
        existing.count += 1;
        if (!existing.symbols.includes(base)) {
          existing.symbols.push(base);
        }
      }
    }
  }

  const sectors = Array.from(sectorMap.values());
  const totalPositions = data?.positions.length ?? 0;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-gray-400">
          Exposure Heatmap
        </h2>
        {isLoading && (
          <span className="text-xs text-gray-500" aria-label="Loading exposure data">
            Loading…
          </span>
        )}
        {!isLoading && (
          <span className="text-xs text-gray-500">
            {totalPositions} open position{totalPositions !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {isError && (
        <p className="py-6 text-center text-xs text-bearish" role="alert">
          Failed to load positions. Retrying…
        </p>
      )}

      {!isError && (
        <div
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
          role="list"
          aria-label="Sector exposure heatmap"
        >
          {sectors.map((sector) => {
            const { label, cardClass, badgeClass } = getConcentration(sector.count);
            return (
              <div
                key={sector.name}
                role="listitem"
                className={`rounded-md border p-3 transition-colors ${cardClass}`}
                aria-label={`${sector.name}: ${sector.count} positions, ${label}`}
              >
                <div className="mb-2 flex items-center justify-between gap-1">
                  <span className="truncate text-xs font-semibold text-white">
                    {sector.name}
                  </span>
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase leading-none ${badgeClass}`}>
                    {label}
                  </span>
                </div>

                <p className="mb-1 text-xl font-bold tabular-nums text-white">
                  {sector.count}
                  <span className="ml-1 text-xs font-normal text-gray-400">pos</span>
                </p>

                {sector.symbols.length > 0 ? (
                  <p className="truncate text-[10px] text-gray-500" title={sector.symbols.join(", ")}>
                    {sector.symbols.join(", ")}
                  </p>
                ) : (
                  <p className="text-[10px] text-gray-600">No exposure</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
