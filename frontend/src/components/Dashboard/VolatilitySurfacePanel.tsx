/**
 * Volatility Surface Viewer
 * Implied volatility across strikes × expiries from Deribit options.
 * Renders as a colour-coded grid (call-side IV per expiry / delta bucket).
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import axios from "axios";

interface DeribitTicker {
  instrument_name: string;
  mark_iv: number;
  underlying_price: number;
  strike: number;
  expiration_timestamp: number;
}

const CURRENCIES = ["BTC", "ETH"] as const;
type Currency = (typeof CURRENCIES)[number];

// Deribit public API (no auth required for market data)
async function fetchDeribitInstruments(currency: Currency): Promise<DeribitTicker[]> {
  const { data } = await axios.get("https://www.deribit.com/api/v2/public/get_instruments", {
    params: { currency, kind: "option", expired: false },
  });
  const instruments: { instrument_name: string; expiration_timestamp: number; strike: number }[] =
    data.result ?? [];

  // Take nearest 4 expiries, options near 25Δ (use 0.8×spot and 1.2×spot as proxies)
  const expiries = [...new Set(instruments.map((i) => i.expiration_timestamp))].sort().slice(0, 5);

  const tickers: DeribitTicker[] = [];
  for (const exp of expiries) {
    const inExp = instruments.filter(
      (i) => i.expiration_timestamp === exp && i.instrument_name.endsWith("-C"),
    );
    // sample ~5 strikes per expiry
    const strikes = inExp.map((i) => i.strike).sort((a, b) => a - b);
    const sample = strikes.length <= 5 ? strikes : [
      strikes[0]!,
      strikes[Math.floor(strikes.length * 0.25)]!,
      strikes[Math.floor(strikes.length * 0.5)]!,
      strikes[Math.floor(strikes.length * 0.75)]!,
      strikes[strikes.length - 1]!,
    ];

    for (const strike of sample) {
      const inst = inExp.find((i) => i.strike === strike);
      if (!inst) continue;
      try {
        const { data: td } = await axios.get("https://www.deribit.com/api/v2/public/ticker", {
          params: { instrument_name: inst.instrument_name },
        });
        const r = td.result;
        if (r.mark_iv > 0) {
          tickers.push({
            instrument_name: inst.instrument_name,
            mark_iv: r.mark_iv,
            underlying_price: r.underlying_price,
            strike,
            expiration_timestamp: exp,
          });
        }
      } catch { /* skip */ }
    }
  }
  return tickers;
}

function ivColor(iv: number): string {
  if (iv > 100) return "bg-red-600/80 text-white";
  if (iv > 80)  return "bg-red-500/60 text-white";
  if (iv > 60)  return "bg-orange-500/60 text-white";
  if (iv > 40)  return "bg-amber-400/50 text-white";
  if (iv > 25)  return "bg-yellow-400/40 text-gray-900";
  if (iv > 0)   return "bg-green-500/30 text-white";
  return "bg-white/5 text-gray-500";
}

function formatExpiry(ts: number): string {
  return new Date(ts).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function VolatilitySurfacePanel() {
  const [currency, setCurrency] = useState<Currency>("BTC");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["vol-surface", currency],
    queryFn: () => fetchDeribitInstruments(currency),
    refetchInterval: 5 * 60_000,
    staleTime: 2 * 60_000,
    retry: false,
  });

  // Build grid: rows = strikes, cols = expiries
  const expiries = [...new Set((data ?? []).map((t) => t.expiration_timestamp))].sort().slice(0, 5);
  const strikes  = [...new Set((data ?? []).map((t) => t.strike))].sort((a, b) => a - b);

  const ivMap = new Map<string, number>();
  for (const t of data ?? []) {
    ivMap.set(`${t.expiration_timestamp}-${t.strike}`, t.mark_iv);
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Volatility Surface</h2>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500">via Deribit</span>
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value as Currency)}
            className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
            aria-label="Select currency"
          >
            {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>
      <p className="mb-3 text-[10px] text-gray-500">
        Implied vol (%) by strike × expiry. Green = low IV, red = high IV.
      </p>

      {isError && (
        <p className="text-xs text-amber-400">
          Deribit data unavailable (may be geo-restricted). Showing placeholder.
        </p>
      )}

      {isLoading ? (
        <div className="h-40 animate-pulse rounded bg-white/5" />
      ) : strikes.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-600">No options data available.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0.5 text-[9px]">
            <thead>
              <tr>
                <th className="text-left text-gray-500 pb-1 pr-2">Strike</th>
                {expiries.map((exp) => (
                  <th key={exp} className="text-center text-gray-500 pb-1 px-1">{formatExpiry(exp)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {strikes.map((strike) => (
                <tr key={strike}>
                  <td className="text-right pr-2 font-mono text-gray-400">{strike.toLocaleString()}</td>
                  {expiries.map((exp) => {
                    const iv = ivMap.get(`${exp}-${strike}`);
                    return (
                      <td
                        key={exp}
                        className={`rounded px-1.5 py-1 text-center font-mono ${iv ? ivColor(iv) : "text-gray-600"}`}
                        title={iv ? `IV: ${iv.toFixed(1)}%` : "No data"}
                      >
                        {iv ? iv.toFixed(0) : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex items-center gap-3 text-[9px] text-gray-500">
            {[
              { label: "<25%",  cls: "bg-green-500/30" },
              { label: "25–40%", cls: "bg-yellow-400/40" },
              { label: "40–60%", cls: "bg-amber-400/50" },
              { label: "60–80%", cls: "bg-orange-500/60" },
              { label: ">80%",  cls: "bg-red-600/80" },
            ].map(({ label, cls }) => (
              <div key={label} className="flex items-center gap-1">
                <div className={`h-2 w-3 rounded ${cls}`} />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
