/**
 * DeltaNeutralCalculator
 * Client-side calculator for delta-neutral hedge positions.
 * No API calls — pure calculation component.
 *
 * Formulas:
 *   required_short = spot_position_usd / spot_entry_price
 *   funding_yield_annual = funding_rate_8h * 3 * 365 * 100 (%)
 *   monthly_income = spot_position_usd * funding_yield_annual / 100 / 12
 */

import { useMemo, useState } from "react";

// --------------- Types ---------------

interface CalcResult {
  requiredShortQty: number;
  fundingYieldAnnual: number;
  fundingYieldMonthly: number;
  monthlyIncome: number;
  liquidationPriceEstimate: number;
  fundingNegative: boolean;
}

// --------------- Helpers ---------------

function formatUSD(value: number): string {
  return value.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function calculate(
  spotPositionUSD: number,
  spotEntryPrice: number,
  fundingRate8h: number,
  targetDelta: number,
  leverage: number
): CalcResult {
  const spotQty = spotEntryPrice > 0 ? spotPositionUSD / spotEntryPrice : 0;
  const requiredShortQty = Math.max(0, spotQty - targetDelta);

  // Annual yield: funding paid 3x per day * 365 days
  const fundingYieldAnnual = fundingRate8h * 3 * 365 * 100;
  const fundingYieldMonthly = fundingYieldAnnual / 12;
  const monthlyIncome = (spotPositionUSD * fundingYieldAnnual) / 100 / 12;

  // Simplified liquidation estimate for short position
  // At leverage L: liq price ≈ entry * (1 + 1/L * 0.9) — simplified
  const liquidationPriceEstimate =
    spotEntryPrice > 0 && leverage > 0
      ? spotEntryPrice * (1 + (0.9 / leverage))
      : 0;

  return {
    requiredShortQty,
    fundingYieldAnnual,
    fundingYieldMonthly,
    monthlyIncome,
    liquidationPriceEstimate,
    fundingNegative: fundingRate8h < 0,
  };
}

// --------------- Input Row ---------------

interface InputRowProps {
  label: string;
  id: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  step?: number;
  suffix?: string;
  helpText?: string;
}

function InputRow({ label, id, value, onChange, min = 0, step = 1, suffix, helpText }: InputRowProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-gray-400">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="number"
          min={min}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          className="w-full rounded border border-border bg-gray-800 px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
          aria-describedby={helpText ? `${id}-help` : undefined}
        />
        {suffix && (
          <span className="shrink-0 text-xs text-gray-500 w-10">{suffix}</span>
        )}
      </div>
      {helpText && (
        <p id={`${id}-help`} className="mt-0.5 text-[10px] text-gray-600">{helpText}</p>
      )}
    </div>
  );
}

// --------------- Result Row ---------------

interface ResultRowProps {
  label: string;
  value: string;
  highlight?: boolean;
  color?: string;
}

function ResultRow({ label, value, highlight, color }: ResultRowProps) {
  return (
    <div className={`flex items-center justify-between rounded px-3 py-2 ${highlight ? "bg-blue-500/10 border border-blue-500/20" : "bg-gray-800/60"}`}>
      <span className="text-xs text-gray-400">{label}</span>
      <span className={`font-mono text-sm font-semibold ${color ?? "text-white"}`}>{value}</span>
    </div>
  );
}

// --------------- Main Component ---------------

export default function DeltaNeutralCalculator() {
  const [spotPositionUSD, setSpotPositionUSD] = useState(10000);
  const [spotEntryPrice, setSpotEntryPrice] = useState(65000);
  const [fundingRate8h, setFundingRate8h] = useState(0.01);
  const [targetDelta, setTargetDelta] = useState(0);
  const [leverage, setLeverage] = useState(5);

  const result = useMemo(
    () => calculate(spotPositionUSD, spotEntryPrice, fundingRate8h, targetDelta, leverage),
    [spotPositionUSD, spotEntryPrice, fundingRate8h, targetDelta, leverage]
  );

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      {/* Header */}
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-white">Delta-Neutral Calculator</h2>
        <p className="mt-0.5 text-xs text-gray-500">
          Calculate hedge size and funding yield for delta-neutral positions
        </p>
      </div>

      {/* Negative funding alert */}
      {result.fundingNegative && (
        <div
          className="mb-4 flex items-center gap-2 rounded border border-red-500/40 bg-red-500/10 px-3 py-2"
          role="alert"
          aria-live="polite"
        >
          <span className="text-lg text-red-400" aria-hidden="true">!</span>
          <div>
            <p className="text-xs font-bold text-red-400">UNWIND ALERT</p>
            <p className="text-[10px] text-red-300">
              Funding rate is negative — you are PAYING to hold the short. Consider closing the hedge.
            </p>
          </div>
        </div>
      )}

      {/* Inputs */}
      <div className="mb-4 space-y-3">
        <InputRow
          label="Spot Position Size (USD)"
          id="spot-position-usd"
          value={spotPositionUSD}
          onChange={setSpotPositionUSD}
          step={100}
          suffix="USD"
          helpText="Total value of your spot holdings"
        />
        <InputRow
          label="Spot Entry Price"
          id="spot-entry-price"
          value={spotEntryPrice}
          onChange={setSpotEntryPrice}
          step={100}
          suffix="USD"
          helpText="Average cost basis of spot position"
        />
        <InputRow
          label="Funding Rate (8h %)"
          id="funding-rate"
          value={fundingRate8h}
          onChange={setFundingRate8h}
          step={0.001}
          suffix="%"
          helpText="Current 8-hour funding rate (negative = short earns)"
        />
        <InputRow
          label="Target Delta"
          id="target-delta"
          value={targetDelta}
          onChange={setTargetDelta}
          min={-1000}
          step={0.01}
          suffix="qty"
          helpText="0 = fully neutral"
        />
        <InputRow
          label="Perp Leverage (for liq. calc)"
          id="leverage"
          value={leverage}
          onChange={setLeverage}
          min={1}
          step={1}
          suffix="x"
          helpText="Leverage used for the short position"
        />
      </div>

      {/* Results */}
      <div className="space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 mb-2">
          Calculated Results
        </p>

        <ResultRow
          label="Required Perp Short (qty)"
          value={result.requiredShortQty.toFixed(6)}
          highlight
        />
        <ResultRow
          label="Annual Funding Yield"
          value={`${result.fundingYieldAnnual.toFixed(2)}%`}
          color={result.fundingNegative ? "text-red-400" : result.fundingYieldAnnual > 10 ? "text-green-400" : "text-yellow-400"}
        />
        <ResultRow
          label="Monthly Yield"
          value={`${result.fundingYieldMonthly.toFixed(2)}%`}
          color={result.fundingNegative ? "text-red-400" : "text-gray-200"}
        />
        <ResultRow
          label="Est. Monthly Income"
          value={formatUSD(result.monthlyIncome)}
          color={result.fundingNegative ? "text-red-400" : "text-green-400"}
        />
        <ResultRow
          label="Liq. Price (Short)"
          value={result.liquidationPriceEstimate > 0 ? `$${result.liquidationPriceEstimate.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}
          color="text-red-400"
        />
      </div>

      {/* Disclaimer */}
      <p className="mt-3 text-[10px] text-gray-600 italic">
        Calculations are estimates only. Liquidation price depends on exchange margin rules. Always verify with your exchange.
      </p>
    </div>
  );
}
