/**
 * Risk-Adjusted Position Sizer
 * Given account size, risk %, ATR, and signal confidence → outputs
 * exact qty in coins and notional USD.
 *
 * Formula: qty = (account × risk%) / (ATR × atr_multiplier)
 * Confidence scales risk: low confidence reduces size by up to 50%.
 */

import { useState, useMemo } from "react";
import { fmtUSD, fmtNumber } from "../../lib/format";

interface SizerResult {
  riskUsd: number;
  stopUsd: number;
  qty: number;
  notional: number;
  kellySuggested: number;
  riskPct: number;
}

function computeSize(
  accountSize: number,
  riskPct: number,
  entryPrice: number,
  atr: number,
  atrMult: number,
  confidence: number,
): SizerResult | null {
  if (!accountSize || !entryPrice || !atr || atrMult <= 0) return null;
  const confScale = 0.5 + (confidence / 100) * 0.5; // 0.5–1.0
  const effectiveRisk = (riskPct / 100) * confScale;
  const riskUsd = accountSize * effectiveRisk;
  const stopUsd = atr * atrMult;
  if (stopUsd <= 0) return null;
  const qty = riskUsd / stopUsd;
  const notional = qty * entryPrice;
  const kellySuggested = Math.min(effectiveRisk * 100 * 0.5, 5); // half-Kelly cap
  return { riskUsd, stopUsd, qty, notional, kellySuggested, riskPct: effectiveRisk * 100 };
}

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-background px-3 py-2 text-center">
      <p className="text-[10px] text-gray-500">{label}</p>
      <p className="font-mono text-xs font-bold text-white">{value}</p>
    </div>
  );
}

export function RiskPositionSizerWidget() {
  const [account, setAccount] = useState("10000");
  const [risk, setRisk] = useState("1");
  const [entry, setEntry] = useState("65000");
  const [atr, setAtr] = useState("800");
  const [atrMult, setAtrMult] = useState("1.5");
  const [confidence, setConfidence] = useState("75");

  const result = useMemo(() =>
    computeSize(
      parseFloat(account) || 0,
      parseFloat(risk) || 0,
      parseFloat(entry) || 0,
      parseFloat(atr) || 0,
      parseFloat(atrMult) || 0,
      parseFloat(confidence) || 75,
    ), [account, risk, entry, atr, atrMult, confidence]);

  const inputCls = "w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-white">Risk Position Sizer</h2>
      <p className="mb-3 text-[10px] text-gray-500">
        Confidence-scaled sizing: low-confidence signals get smaller allocations.
      </p>

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {[
          { label: "Account ($)", value: account, set: setAccount },
          { label: "Risk %", value: risk, set: setRisk },
          { label: "Entry Price ($)", value: entry, set: setEntry },
          { label: "ATR ($)", value: atr, set: setAtr },
          { label: "ATR Multiplier", value: atrMult, set: setAtrMult },
          { label: "Confidence %", value: confidence, set: setConfidence },
        ].map(({ label, value, set }) => (
          <div key={label}>
            <label className="mb-0.5 block text-[10px] text-gray-500">{label}</label>
            <input
              type="number"
              value={value}
              onChange={(e) => { set(e.target.value); }}
              className={inputCls}
              aria-label={label}
            />
          </div>
        ))}
      </div>

      {result ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <StatBox label="Effective Risk %" value={`${result.riskPct.toFixed(2)}%`} />
          <StatBox label="Risk $" value={fmtUSD(result.riskUsd)} />
          <StatBox label="Stop Distance ($)" value={fmtUSD(result.stopUsd)} />
          <StatBox label="Quantity (coins)" value={fmtNumber(result.qty, { decimals: 4 })} />
          <StatBox label="Notional $" value={fmtUSD(result.notional)} />
          <StatBox label="Half-Kelly %" value={`${result.kellySuggested.toFixed(2)}%`} />
        </div>
      ) : (
        <p className="py-4 text-center text-xs text-gray-600">Fill all fields to see sizing.</p>
      )}
    </div>
  );
}
