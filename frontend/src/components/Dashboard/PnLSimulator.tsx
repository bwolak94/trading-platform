import { useMemo, useState } from "react";

interface SimulationInputs {
  entryPrice: string;
  stopLoss: string;
  takeProfit: string;
  positionSize: string;
  leverage: string;
}

interface SimulationResult {
  profitIfTp: number;
  lossIfSl: number;
  riskRewardRatio: number;
  breakevenPrice: number;
  riskPct: number;
  rewardPct: number;
}

function parseNum(val: string): number {
  const n = parseFloat(val);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function computeSimulation(inputs: SimulationInputs): SimulationResult | null {
  const entry = parseNum(inputs.entryPrice);
  const sl = parseNum(inputs.stopLoss);
  const tp = parseNum(inputs.takeProfit);
  const size = parseNum(inputs.positionSize);
  const lev = parseNum(inputs.leverage);

  if (entry === 0 || sl === 0 || tp === 0 || size === 0 || lev === 0) return null;
  if (sl === entry || tp === entry) return null;

  const isLong = tp > entry;
  const effectiveSize = size * lev;
  const qty = effectiveSize / entry;

  const profitIfTp = isLong
    ? qty * (tp - entry)
    : qty * (entry - tp);

  const lossIfSl = isLong
    ? qty * (entry - sl)
    : qty * (sl - entry);

  const riskRewardRatio = lossIfSl !== 0 ? Math.abs(profitIfTp / lossIfSl) : 0;

  // Breakeven includes a rough fee estimate (0.1% round trip)
  const feeRate = 0.001;
  const totalFees = effectiveSize * feeRate;
  const breakevenPrice = isLong
    ? entry + totalFees / qty
    : entry - totalFees / qty;

  const riskPct = Math.abs(lossIfSl / size) * 100;
  const rewardPct = Math.abs(profitIfTp / size) * 100;

  return {
    profitIfTp,
    lossIfSl: -Math.abs(lossIfSl),
    riskRewardRatio,
    breakevenPrice,
    riskPct,
    rewardPct,
  };
}

function fmtUsd(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}$${Math.abs(v).toFixed(2)}`;
}

export function PnLSimulator() {
  const [inputs, setInputs] = useState<SimulationInputs>({
    entryPrice: "",
    stopLoss: "",
    takeProfit: "",
    positionSize: "1000",
    leverage: "1",
  });

  const result = useMemo(() => computeSimulation(inputs), [inputs]);

  const updateField = (field: keyof SimulationInputs, value: string) => {
    setInputs((prev) => ({ ...prev, [field]: value }));
  };

  // Bar widths for visual risk/reward display
  const totalSpan = result
    ? Math.abs(result.lossIfSl) + Math.abs(result.profitIfTp)
    : 0;
  const riskBarPct = result && totalSpan > 0
    ? (Math.abs(result.lossIfSl) / totalSpan) * 100
    : 50;
  const rewardBarPct = result && totalSpan > 0
    ? (Math.abs(result.profitIfTp) / totalSpan) * 100
    : 50;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-medium uppercase tracking-wide text-gray-500">
        PnL Simulator
      </h3>

      {/* Input fields in a compact 2-col grid */}
      <div className="mb-4 grid grid-cols-2 gap-3">
        <InputField
          label="Entry Price"
          value={inputs.entryPrice}
          onChange={(v) => updateField("entryPrice", v)}
          placeholder="e.g. 65000"
        />
        <InputField
          label="Stop Loss"
          value={inputs.stopLoss}
          onChange={(v) => updateField("stopLoss", v)}
          placeholder="e.g. 63500"
        />
        <InputField
          label="Take Profit"
          value={inputs.takeProfit}
          onChange={(v) => updateField("takeProfit", v)}
          placeholder="e.g. 68000"
        />
        <InputField
          label="Position Size (USD)"
          value={inputs.positionSize}
          onChange={(v) => updateField("positionSize", v)}
          placeholder="e.g. 1000"
        />
        <InputField
          label="Leverage"
          value={inputs.leverage}
          onChange={(v) => updateField("leverage", v)}
          placeholder="e.g. 10"
        />
      </div>

      {/* Results */}
      {result ? (
        <div className="space-y-3">
          {/* Risk vs Reward visual bar */}
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-500">
              <span>Risk</span>
              <span>Reward</span>
            </div>
            <div className="flex h-3 w-full overflow-hidden rounded-full">
              <div
                className="bg-bearish transition-all duration-300"
                style={{ width: `${riskBarPct}%` }}
                role="progressbar"
                aria-label={`Risk: ${result.riskPct.toFixed(1)}%`}
                aria-valuenow={riskBarPct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
              <div
                className="bg-bullish transition-all duration-300"
                style={{ width: `${rewardBarPct}%` }}
                role="progressbar"
                aria-label={`Reward: ${result.rewardPct.toFixed(1)}%`}
                aria-valuenow={rewardBarPct}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
            <div className="flex justify-between text-xs font-mono">
              <span className="text-bearish">{result.riskPct.toFixed(1)}%</span>
              <span className="text-bullish">{result.rewardPct.toFixed(1)}%</span>
            </div>
          </div>

          {/* Numeric results */}
          <div className="grid grid-cols-2 gap-2">
            <ResultCard
              label="Profit if TP hit"
              value={fmtUsd(result.profitIfTp)}
              colorClass="text-bullish"
            />
            <ResultCard
              label="Loss if SL hit"
              value={fmtUsd(result.lossIfSl)}
              colorClass="text-bearish"
            />
            <ResultCard
              label="Risk/Reward"
              value={`1:${result.riskRewardRatio.toFixed(2)}`}
              colorClass={result.riskRewardRatio >= 2 ? "text-bullish" : result.riskRewardRatio >= 1 ? "text-yellow-400" : "text-bearish"}
            />
            <ResultCard
              label="Breakeven"
              value={`$${result.breakevenPrice.toFixed(2)}`}
              colorClass="text-gray-300"
            />
          </div>
        </div>
      ) : (
        <div className="rounded border border-border bg-background/50 p-4 text-center text-xs text-gray-500">
          Enter entry, stop loss, take profit, position size, and leverage to simulate
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

interface InputFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}

function InputField({ label, value, onChange, placeholder }: InputFieldProps) {
  return (
    <div>
      <label className="mb-1 block text-xs text-gray-500">{label}</label>
      <input
        type="number"
        step="any"
        min="0"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm font-mono text-white placeholder-gray-600 focus:border-accent focus:outline-none"
        aria-label={label}
      />
    </div>
  );
}

interface ResultCardProps {
  label: string;
  value: string;
  colorClass: string;
}

function ResultCard({ label, value, colorClass }: ResultCardProps) {
  return (
    <div className="rounded border border-border bg-background/50 px-3 py-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-sm font-mono font-semibold ${colorClass}`}>{value}</div>
    </div>
  );
}
