/**
 * B7: Tick-by-Tick Replay
 *
 * Step through 1-minute candles one at a time with Play/Pause/Speed buttons.
 * Uses existing OHLCV API with sequential fetches.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bar,
  ComposedChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

async function fetchCandles(symbol: string, limit: number): Promise<Candle[]> {
  const resp = await fetch(
    `/api/v1/market/ohlcv?symbol=${encodeURIComponent(symbol)}&timeframe=1m&limit=${limit}`,
  );
  if (!resp.ok) throw new Error("Failed to fetch candles");
  const data: unknown = await resp.json();
  return Array.isArray(data) ? (data as Candle[]) : ((data as { data: Candle[] }).data ?? []);
}

const SPEED_LABELS: Record<number, string> = { 500: "1×", 200: "2.5×", 50: "5×" };

export function TickByTickReplay() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [allCandles, setAllCandles] = useState<Candle[]>([]);
  const [cursor, setCursor] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<500 | 200 | 50>(500);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadCandles = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPlaying(false);
    try {
      const data = await fetchCandles(symbol, 200);
      setAllCandles(data);
      setCursor(1);
    } catch (e) {
      setError("Failed to load candle data");
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    void loadCandles();
  }, [loadCandles]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (!playing) return;
    intervalRef.current = setInterval(() => {
      setCursor((c) => {
        if (c >= allCandles.length) {
          setPlaying(false);
          return c;
        }
        return c + 1;
      });
    }, speed);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, speed, allCandles.length]);

  const visible = allCandles.slice(0, cursor);
  const currentCandle = allCandles[cursor - 1];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-gray-200">Tick-by-Tick Replay</h3>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-border bg-background px-2 py-0.5 text-xs text-gray-300"
          aria-label="Select asset for replay"
        >
          <option value="BTC/USDT">BTC/USDT</option>
          <option value="ETH/USDT">ETH/USDT</option>
          <option value="SOL/USDT">SOL/USDT</option>
        </select>

        <div className="flex items-center gap-1 ml-auto">
          <button
            type="button"
            onClick={() => setCursor((c) => Math.max(1, c - 1))}
            disabled={cursor <= 1}
            className="rounded border border-border px-2 py-0.5 text-xs text-gray-400 hover:text-white disabled:opacity-40"
            aria-label="Previous candle"
          >◀</button>
          <button
            type="button"
            onClick={() => setPlaying((p) => !p)}
            className="rounded border border-accent bg-accent/10 px-3 py-0.5 text-xs font-semibold text-accent hover:bg-accent/20"
            aria-label={playing ? "Pause replay" : "Play replay"}
          >
            {playing ? "⏸ Pause" : "▶ Play"}
          </button>
          <button
            type="button"
            onClick={() => setCursor((c) => Math.min(allCandles.length, c + 1))}
            disabled={cursor >= allCandles.length}
            className="rounded border border-border px-2 py-0.5 text-xs text-gray-400 hover:text-white disabled:opacity-40"
            aria-label="Next candle"
          >▶</button>
          <select
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value) as 500 | 200 | 50)}
            className="rounded border border-border bg-background px-1.5 py-0.5 text-xs text-gray-300"
            aria-label="Replay speed"
          >
            {Object.entries(SPEED_LABELS).map(([ms, label]) => (
              <option key={ms} value={ms}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {loading && <div className="flex h-32 items-center justify-center text-xs text-gray-500">Loading candles…</div>}
      {error && <div className="flex h-32 items-center justify-center text-xs text-bearish">{error}</div>}

      {!loading && !error && (
        <>
          <div className="mb-2 flex gap-4 text-xs text-gray-400">
            <span>Candle {cursor} / {allCandles.length}</span>
            {currentCandle && (
              <>
                <span className="font-mono">{new Date(currentCandle.timestamp).toLocaleTimeString()}</span>
                <span className={currentCandle.close >= currentCandle.open ? "text-bullish" : "text-bearish"}>
                  C: {currentCandle.close.toLocaleString()}
                </span>
                <span>Vol: {(currentCandle.volume / 1000).toFixed(1)}K</span>
              </>
            )}
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <ComposedChart data={visible} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="timestamp" tick={false} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
                formatter={(v: number) => [v.toLocaleString(), ""]}
              />
              <Bar
                dataKey="close"
                fill="#22d3ee"
                maxBarSize={8}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <input
            type="range"
            min={1}
            max={allCandles.length || 1}
            value={cursor}
            onChange={(e) => { setPlaying(false); setCursor(Number(e.target.value)); }}
            className="mt-2 w-full accent-accent"
            aria-label="Scrub replay position"
          />
        </>
      )}
    </div>
  );
}
