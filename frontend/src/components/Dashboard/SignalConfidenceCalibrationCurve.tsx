/**
 * B1: Signal Confidence Calibration Curve
 *
 * Reliability diagram: buckets signals by confidence (0-10%, 10-20%, …, 90-100%)
 * and plots actual win rate per bucket.  A well-calibrated model sits on the
 * perfect-calibration diagonal.
 */

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useQuery } from "@tanstack/react-query";

interface SignalBucket {
  label: string;
  centerPct: number;
  totalSignals: number;
  wins: number;
  winRate: number;
}

async function fetchCalibrationData(): Promise<SignalBucket[]> {
  const resp = await fetch("/api/v1/analytics/signal-calibration");
  if (!resp.ok) throw new Error("Failed to fetch calibration data");
  return resp.json();
}

export function SignalConfidenceCalibrationCurve() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["signal-calibration"],
    queryFn: fetchCalibrationData,
    staleTime: 5 * 60 * 1000,
  });

  const chartData = useMemo(() => {
    if (!data) return [];
    return data.map((b) => ({
      confidence: b.centerPct,
      winRate: Math.round(b.winRate * 100),
      signals: b.totalSignals,
      label: b.label,
    }));
  }, [data]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-4 text-sm font-semibold text-gray-200">
        Confidence Calibration Curve
      </h3>
      <p className="mb-3 text-xs text-gray-400">
        Actual win rate vs. predicted confidence per bucket. Ideal = diagonal.
      </p>

      {isLoading && (
        <div className="flex h-48 items-center justify-center text-xs text-gray-500">
          Loading calibration data…
        </div>
      )}

      {isError && (
        <div className="flex h-48 items-center justify-center text-xs text-bearish">
          Failed to load calibration data
        </div>
      )}

      {!isLoading && !isError && chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="confidence"
              tickFormatter={(v) => `${v}%`}
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              label={{ value: "Confidence", position: "insideBottom", offset: -2, fontSize: 10, fill: "#94a3b8" }}
            />
            <YAxis
              tickFormatter={(v) => `${v}%`}
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              domain={[0, 100]}
            />
            <Tooltip
              contentStyle={{ background: "#1e293b", border: "1px solid #334155", fontSize: 11 }}
              formatter={(value: number, name: string) => [`${value}%`, name === "winRate" ? "Actual Win Rate" : name]}
              labelFormatter={(label) => `Confidence: ${label}%`}
            />
            {/* Perfect calibration reference line */}
            <ReferenceLine
              stroke="#64748b"
              strokeDasharray="4 4"
              segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]}
            />
            <Line
              type="monotone"
              dataKey="winRate"
              stroke="#22d3ee"
              strokeWidth={2}
              dot={{ r: 4, fill: "#22d3ee" }}
              name="winRate"
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {!isLoading && !isError && chartData.length === 0 && (
        <div className="flex h-48 items-center justify-center text-xs text-gray-500">
          Not enough signal history to compute calibration
        </div>
      )}
    </div>
  );
}
