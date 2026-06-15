import { useState, useMemo, useCallback } from "react";

interface RiskInputs {
  capital: string;
  riskPercent: string;
  entryPrice: string;
  stopLossPrice: string;
  takeProfitPrice: string;
  leverage: string;
}

interface ComputedResults {
  positionSizeUsd: number;
  positionSizeUnits: number;
  maxLossUsd: number;
  liquidationPrice: number | null;
  riskRewardRatio: number | null;
}

interface ValidationErrors {
  capital?: string;
  riskPercent?: string;
  entryPrice?: string;
  stopLossPrice?: string;
  leverage?: string;
}

const INITIAL_INPUTS: RiskInputs = {
  capital: "",
  riskPercent: "1",
  entryPrice: "",
  stopLossPrice: "",
  takeProfitPrice: "",
  leverage: "1",
};

function parsePositiveFloat(value: string): number | null {
  const num = parseFloat(value);
  if (isNaN(num) || num < 0) return null;
  return num;
}

function validate(inputs: RiskInputs): ValidationErrors {
  const errors: ValidationErrors = {};
  const capital = parsePositiveFloat(inputs.capital);
  const riskPercent = parsePositiveFloat(inputs.riskPercent);
  const entry = parsePositiveFloat(inputs.entryPrice);
  const sl = parsePositiveFloat(inputs.stopLossPrice);
  const leverage = parsePositiveFloat(inputs.leverage);

  if (inputs.capital !== "" && (capital === null || capital <= 0)) {
    errors.capital = "Must be a positive number";
  }
  if (inputs.riskPercent !== "" && (riskPercent === null || riskPercent <= 0 || riskPercent > 100)) {
    errors.riskPercent = "Must be between 0 and 100";
  }
  if (inputs.entryPrice !== "" && (entry === null || entry <= 0)) {
    errors.entryPrice = "Must be a positive number";
  }
  if (inputs.stopLossPrice !== "" && (sl === null || sl <= 0)) {
    errors.stopLossPrice = "Must be a positive number";
  }
  if (entry !== null && sl !== null && entry === sl) {
    errors.stopLossPrice = "Stop loss must differ from entry";
  }
  if (inputs.leverage !== "" && (leverage === null || leverage < 1 || leverage > 125)) {
    errors.leverage = "Must be between 1 and 125";
  }

  return errors;
}

function compute(inputs: RiskInputs): ComputedResults | null {
  const capital = parsePositiveFloat(inputs.capital);
  const riskPercent = parsePositiveFloat(inputs.riskPercent);
  const entry = parsePositiveFloat(inputs.entryPrice);
  const sl = parsePositiveFloat(inputs.stopLossPrice);
  const leverage = parsePositiveFloat(inputs.leverage);
  const tp = parsePositiveFloat(inputs.takeProfitPrice);

  if (!capital || !riskPercent || !entry || !sl || !leverage) return null;
  if (capital <= 0 || riskPercent <= 0 || entry <= 0 || sl <= 0 || leverage < 1) return null;
  if (entry === sl) return null;

  const riskAmountUsd = capital * (riskPercent / 100);
  const slDistancePercent = Math.abs(entry - sl) / entry;
  const slDistanceWithLeverage = slDistancePercent * leverage;

  if (slDistanceWithLeverage === 0) return null;

  const positionSizeUsd = riskAmountUsd / slDistancePercent;
  const positionSizeUnits = positionSizeUsd / entry;
  const maxLossUsd = riskAmountUsd;

  // Liquidation price (simplified): when unrealized loss = margin (positionSize / leverage)
  // For longs: liq = entry * (1 - 1/leverage)
  // For shorts: liq = entry * (1 + 1/leverage)
  const isLong = sl < entry;
  let liquidationPrice: number | null = null;
  if (leverage > 1) {
    liquidationPrice = isLong
      ? entry * (1 - 1 / leverage)
      : entry * (1 + 1 / leverage);
  }

  let riskRewardRatio: number | null = null;
  if (tp !== null && tp > 0 && tp !== entry) {
    const rewardDistance = Math.abs(tp - entry);
    const riskDistance = Math.abs(entry - sl);
    if (riskDistance > 0) {
      riskRewardRatio = rewardDistance / riskDistance;
    }
  }

  return {
    positionSizeUsd,
    positionSizeUnits,
    maxLossUsd,
    liquidationPrice,
    riskRewardRatio,
  };
}

function formatUsd(value: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatUnits(value: number): string {
  if (value >= 1) {
    return value.toLocaleString("en-US", {
      minimumFractionDigits: 4,
      maximumFractionDigits: 4,
    });
  }
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 6,
    maximumFractionDigits: 8,
  });
}

function formatPrice(value: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  });
}

interface InputFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  placeholder?: string;
  suffix?: string;
  id: string;
}

function InputField({ label, value, onChange, error, placeholder, suffix, id }: InputFieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-[11px] font-medium text-gray-400">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min="0"
          step="any"
          value={value}
          onChange={(e) => { onChange(e.target.value); }}
          placeholder={placeholder}
          className={`w-full rounded border bg-background px-3 py-1.5 font-mono text-xs text-white placeholder-gray-600 outline-none transition-colors focus:ring-1 ${
            error
              ? "border-red-500/50 focus:border-red-500 focus:ring-red-500/30"
              : "border-border focus:border-blue-500 focus:ring-blue-500/30"
          }`}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
        />
        {suffix && (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-500">
            {suffix}
          </span>
        )}
      </div>
      {error && (
        <p id={`${id}-error`} className="mt-0.5 text-[10px] text-red-400" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

interface ResultRowProps {
  label: string;
  value: string;
  highlight?: "green" | "red" | "yellow" | "none";
}

function ResultRow({ label, value, highlight = "none" }: ResultRowProps) {
  const colorClass =
    highlight === "green"
      ? "text-green-400"
      : highlight === "red"
        ? "text-red-400"
        : highlight === "yellow"
          ? "text-yellow-400"
          : "text-white";

  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[11px] text-gray-400">{label}</span>
      <span className={`font-mono text-xs font-semibold ${colorClass}`}>{value}</span>
    </div>
  );
}

export function RiskCalculator() {
  const [inputs, setInputs] = useState<RiskInputs>(INITIAL_INPUTS);

  const updateField = useCallback(
    (field: keyof RiskInputs) => (value: string) => {
      setInputs((prev) => ({ ...prev, [field]: value }));
    },
    []
  );

  const errors = useMemo(() => validate(inputs), [inputs]);
  const hasErrors = Object.keys(errors).length > 0;
  const results = useMemo(() => (hasErrors ? null : compute(inputs)), [inputs, hasErrors]);

  const isLong = useMemo(() => {
    const entry = parsePositiveFloat(inputs.entryPrice);
    const sl = parsePositiveFloat(inputs.stopLossPrice);
    if (!entry || !sl || entry === sl) return null;
    return sl < entry;
  }, [inputs.entryPrice, inputs.stopLossPrice]);

  const handleReset = useCallback(() => {
    setInputs(INITIAL_INPUTS);
  }, []);

  return (
    <div
      className="rounded-lg border border-border bg-surface p-4"
      aria-label="Risk calculator"
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Risk Calculator</h3>
        <button
          onClick={handleReset}
          className="rounded px-2 py-0.5 text-[10px] text-gray-500 transition-colors hover:bg-background hover:text-gray-300"
          aria-label="Reset calculator inputs"
        >
          Reset
        </button>
      </div>

      {/* Direction badge */}
      {isLong !== null && (
        <div className="mb-3">
          <span
            className={`rounded px-2 py-0.5 text-[10px] font-medium ${
              isLong
                ? "bg-green-900/30 text-green-400"
                : "bg-red-900/30 text-red-400"
            }`}
          >
            {isLong ? "LONG" : "SHORT"}
          </span>
        </div>
      )}

      {/* Inputs */}
      <div className="space-y-2.5">
        <InputField
          id="risk-capital"
          label="Capital"
          value={inputs.capital}
          onChange={updateField("capital")}
          error={errors.capital}
          placeholder="10000"
          suffix="USD"
        />

        <InputField
          id="risk-percent"
          label="Risk per trade"
          value={inputs.riskPercent}
          onChange={updateField("riskPercent")}
          error={errors.riskPercent}
          placeholder="1"
          suffix="%"
        />

        <InputField
          id="risk-entry"
          label="Entry price"
          value={inputs.entryPrice}
          onChange={updateField("entryPrice")}
          error={errors.entryPrice}
          placeholder="50000"
        />

        <InputField
          id="risk-sl"
          label="Stop loss"
          value={inputs.stopLossPrice}
          onChange={updateField("stopLossPrice")}
          error={errors.stopLossPrice}
          placeholder="49000"
        />

        <InputField
          id="risk-tp"
          label="Take profit (optional)"
          value={inputs.takeProfitPrice}
          onChange={updateField("takeProfitPrice")}
          placeholder="52000"
        />

        <div>
          <label htmlFor="risk-leverage" className="mb-1 block text-[11px] font-medium text-gray-400">
            Leverage
          </label>
          <div className="flex items-center gap-2">
            <input
              id="risk-leverage"
              type="range"
              min="1"
              max="125"
              step="1"
              value={inputs.leverage || "1"}
              onChange={(e) => { updateField("leverage")(e.target.value); }}
              className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-gray-700 accent-blue-500"
              aria-label="Leverage slider"
            />
            <span className="w-10 text-right font-mono text-xs text-white">
              {inputs.leverage || 1}x
            </span>
          </div>
          {errors.leverage && (
            <p className="mt-0.5 text-[10px] text-red-400" role="alert">
              {errors.leverage}
            </p>
          )}
        </div>
      </div>

      {/* Divider */}
      <div className="my-4 border-t border-border" />

      {/* Results */}
      {results ? (
        <div aria-live="polite" aria-label="Calculation results">
          <ResultRow
            label="Position size"
            value={`$${formatUsd(results.positionSizeUsd)}`}
          />
          <ResultRow
            label="Units"
            value={formatUnits(results.positionSizeUnits)}
          />
          <ResultRow
            label="Max loss"
            value={`-$${formatUsd(results.maxLossUsd)}`}
            highlight="red"
          />
          {results.liquidationPrice !== null && (
            <ResultRow
              label="Liquidation"
              value={`$${formatPrice(results.liquidationPrice)}`}
              highlight="yellow"
            />
          )}
          {results.riskRewardRatio !== null && (
            <ResultRow
              label="Risk / Reward"
              value={`1:${results.riskRewardRatio.toFixed(2)}`}
              highlight={results.riskRewardRatio >= 2 ? "green" : results.riskRewardRatio >= 1 ? "yellow" : "red"}
            />
          )}
        </div>
      ) : (
        <p className="text-center text-[11px] text-gray-600">
          Fill in capital, risk %, entry, and stop loss to see results.
        </p>
      )}
    </div>
  );
}
