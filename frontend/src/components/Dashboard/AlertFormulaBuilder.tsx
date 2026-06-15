/**
 * Visual Alert Formula Builder
 * Create custom alerts with visual condition composer
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import axios from "axios";

// ─── Types ────────────────────────────────────────────────────────────────────

type ConditionType = "RSI" | "VOLUME" | "REGIME" | "CONFIDENCE" | "PRICE";
type Operator = "<" | ">" | "=" | ">=" | "<=";
type LogicOp = "AND" | "OR";
type AlertChannel = "Telegram" | "Discord";

interface Condition {
  id: string;
  type: ConditionType;
  operator: Operator;
  value: string;
  logic: LogicOp;
}

interface SavedAlert {
  id: string;
  name: string;
  formula: string;
  asset: string;
  channel: AlertChannel;
  created_at: string;
}

interface SaveAlertPayload {
  name: string;
  formula: string;
  conditions: Condition[];
  asset: string;
  channel: AlertChannel;
}

interface TestResult {
  matches: boolean;
  reason: string;
}

// ─── API ─────────────────────────────────────────────────────────────────────

async function fetchSavedAlerts(): Promise<{ alerts: SavedAlert[] }> {
  const { data } = await axios.get<{ alerts: SavedAlert[] }>(
    "/api/v1/automation/alert-formula",
  );
  return data;
}

async function saveAlert(payload: SaveAlertPayload): Promise<SavedAlert> {
  const { data } = await axios.post<SavedAlert>(
    "/api/v1/automation/alert-formula",
    payload,
  );
  return data;
}

async function testFormula(
  formula: string,
  asset: string,
): Promise<TestResult> {
  const { data } = await axios.post<TestResult>(
    "/api/v1/automation/alert-formula/test",
    { formula, asset },
  );
  return data;
}

async function deleteAlert(id: string): Promise<void> {
  await axios.delete(`/api/v1/automation/alert-formula/${id}`);
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const CONDITION_DEFAULTS: Record<ConditionType, { operator: Operator; value: string }> = {
  RSI: { operator: "<", value: "30" },
  VOLUME: { operator: ">", value: "2" },
  REGIME: { operator: "=", value: "TREND_BULL" },
  CONFIDENCE: { operator: ">", value: "75" },
  PRICE: { operator: ">", value: "50000" },
};

const CONDITION_LABELS: Record<ConditionType, string> = {
  RSI: "RSI(14)",
  VOLUME: "Volume (x avg)",
  REGIME: "Regime",
  CONFIDENCE: "Confidence %",
  PRICE: "Price",
};

const REGIME_VALUES = [
  "TREND_BULL", "TREND_BEAR", "CONSOLIDATION", "HIGH_VOL_CHOPPY",
];

function buildFormula(conditions: Condition[]): string {
  return conditions
    .map((c, i) => {
      const prefix = i === 0 ? "" : ` ${c.logic} `;
      const label = CONDITION_LABELS[c.type];
      return `${prefix}${label} ${c.operator} ${c.value}`;
    })
    .join("");
}

function generateId(): string {
  return `cond-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

const ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
const CONDITION_TYPES: ConditionType[] = ["RSI", "VOLUME", "REGIME", "CONFIDENCE", "PRICE"];
const OPERATORS: Operator[] = ["<", ">", "=", ">=", "<="];
const CHANNELS: AlertChannel[] = ["Telegram", "Discord"];

// ─── Sub-components ──────────────────────────────────────────────────────────

function ConditionRow({
  condition,
  index,
  onChange,
  onRemove,
}: {
  condition: Condition;
  index: number;
  onChange: (id: string, field: keyof Condition, val: string) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded border border-border/50 bg-surface/50 p-2">
      {index > 0 && (
        <select
          value={condition.logic}
          onChange={(e) => { onChange(condition.id, "logic", e.target.value); }}
          className="rounded border border-border bg-background px-1.5 py-0.5 text-xs text-accent focus:outline-none"
          aria-label="Logical operator"
        >
          {(["AND", "OR"] as LogicOp[]).map((op) => (
            <option key={op} value={op}>
              {op}
            </option>
          ))}
        </select>
      )}

      <select
        value={condition.type}
        onChange={(e) => { onChange(condition.id, "type", e.target.value); }}
        className="rounded border border-border bg-background px-1.5 py-0.5 text-xs text-gray-300 focus:outline-none"
        aria-label="Condition type"
      >
        {CONDITION_TYPES.map((t) => (
          <option key={t} value={t}>
            {CONDITION_LABELS[t]}
          </option>
        ))}
      </select>

      {condition.type !== "REGIME" ? (
        <>
          <select
            value={condition.operator}
            onChange={(e) => { onChange(condition.id, "operator", e.target.value); }}
            className="w-12 rounded border border-border bg-background px-1 py-0.5 text-xs text-gray-300 focus:outline-none"
            aria-label="Operator"
          >
            {OPERATORS.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={condition.value}
            onChange={(e) => { onChange(condition.id, "value", e.target.value); }}
            className="w-20 rounded border border-border bg-background px-1.5 py-0.5 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-accent"
            aria-label="Condition value"
          />
        </>
      ) : (
        <>
          <span className="text-xs text-gray-500">=</span>
          <select
            value={condition.value}
            onChange={(e) => { onChange(condition.id, "value", e.target.value); }}
            className="rounded border border-border bg-background px-1.5 py-0.5 text-xs text-gray-300 focus:outline-none"
            aria-label="Regime value"
          >
            {REGIME_VALUES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </>
      )}

      <button
        type="button"
        onClick={() => { onRemove(condition.id); }}
        className="ml-auto rounded border border-bearish/30 px-1.5 py-0.5 text-[10px] text-bearish transition-colors hover:bg-bearish/10"
        aria-label="Remove condition"
      >
        ✕
      </button>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function AlertFormulaBuilder() {
  const [conditions, setConditions] = useState<Condition[]>([
    {
      id: generateId(),
      type: "RSI",
      operator: "<",
      value: "30",
      logic: "AND",
    },
  ]);
  const [alertName, setAlertName] = useState("");
  const [selectedAsset, setSelectedAsset] = useState("BTCUSDT");
  const [selectedChannel, setSelectedChannel] = useState<AlertChannel>("Telegram");
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  const formula = buildFormula(conditions);

  const { data: savedData, refetch } = useQuery({
    queryKey: ["saved-alerts"],
    queryFn: fetchSavedAlerts,
    retry: false,
  });

  const saveMutation = useMutation({
    mutationFn: saveAlert,
    onSuccess: () => {
      void refetch();
      setAlertName("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAlert,
    onSuccess: () => { void refetch(); },
  });

  const testMutation = useMutation({
    mutationFn: ({ f, a }: { f: string; a: string }) => testFormula(f, a),
    onSuccess: (result) => { setTestResult(result); },
  });

  const handleAddCondition = useCallback(() => {
    const newCond: Condition = {
      id: generateId(),
      type: "CONFIDENCE",
      ...CONDITION_DEFAULTS.CONFIDENCE,
      logic: "AND",
    };
    setConditions((prev) => [...prev, newCond]);
  }, []);

  const handleConditionChange = useCallback(
    (id: string, field: keyof Condition, val: string) => {
      setConditions((prev) =>
        prev.map((c) => {
          if (c.id !== id) return c;
          if (field === "type") {
            const defaults = CONDITION_DEFAULTS[val as ConditionType];
            return { ...c, type: val as ConditionType, ...defaults };
          }
          return { ...c, [field]: val };
        }),
      );
      setTestResult(null);
    },
    [],
  );

  const handleRemoveCondition = useCallback((id: string) => {
    setConditions((prev) => prev.filter((c) => c.id !== id));
  }, []);

  const handleSave = useCallback(() => {
    if (!alertName.trim() || conditions.length === 0) return;
    saveMutation.mutate({
      name: alertName.trim(),
      formula,
      conditions,
      asset: selectedAsset,
      channel: selectedChannel,
    });
  }, [alertName, conditions, formula, selectedAsset, selectedChannel, saveMutation]);

  const handleTest = useCallback(() => {
    testMutation.mutate({ f: formula, a: selectedAsset });
  }, [formula, selectedAsset, testMutation]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-4 text-sm font-semibold text-white">Alert Formula Builder</h2>

      {/* Conditions */}
      <div className="mb-3 space-y-2">
        {conditions.map((cond, idx) => (
          <ConditionRow
            key={cond.id}
            condition={cond}
            index={idx}
            onChange={handleConditionChange}
            onRemove={handleRemoveCondition}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={handleAddCondition}
        className="mb-4 flex items-center gap-1 text-xs text-accent hover:text-white transition-colors"
        aria-label="Add condition"
      >
        <span className="text-base leading-none">+</span> Add Condition
      </button>

      {/* Formula preview */}
      <div className="mb-4 rounded border border-border/50 bg-background p-2">
        <p className="text-[10px] text-gray-500 mb-1">Formula Preview</p>
        <code className="text-xs text-accent break-all">{formula || "—"}</code>
      </div>

      {/* Test result */}
      {testResult && (
        <div
          className={`mb-3 rounded px-3 py-2 text-xs ${
            testResult.matches
              ? "bg-bullish/10 text-bullish"
              : "bg-bearish/10 text-bearish"
          }`}
        >
          {testResult.matches ? "Match:" : "No match:"} {testResult.reason}
        </div>
      )}

      {/* Config row */}
      <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <input
          type="text"
          value={alertName}
          onChange={(e) => { setAlertName(e.target.value); }}
          placeholder="Alert name…"
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-accent"
          aria-label="Alert name"
        />
        <select
          value={selectedAsset}
          onChange={(e) => { setSelectedAsset(e.target.value); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
          aria-label="Target asset"
        >
          {ASSETS.map((a) => (
            <option key={a} value={a}>
              {a.replace("USDT", "")}
            </option>
          ))}
        </select>
        <select
          value={selectedChannel}
          onChange={(e) => { setSelectedChannel(e.target.value as AlertChannel); }}
          className="rounded border border-border bg-background px-2 py-1 text-xs text-gray-300 focus:outline-none"
          aria-label="Notification channel"
        >
          {CHANNELS.map((ch) => (
            <option key={ch} value={ch}>
              {ch}
            </option>
          ))}
        </select>
      </div>

      {/* Action buttons */}
      <div className="mb-6 flex gap-2">
        <button
          type="button"
          onClick={handleTest}
          disabled={testMutation.isPending || conditions.length === 0}
          className="flex-1 rounded border border-border bg-background py-1.5 text-xs font-medium text-gray-300 transition-colors hover:border-accent hover:text-white disabled:opacity-50"
          aria-label="Test formula against current data"
        >
          {testMutation.isPending ? "Testing…" : "Test"}
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saveMutation.isPending || !alertName.trim() || conditions.length === 0}
          className="flex-1 rounded border border-accent bg-accent/10 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
          aria-label="Save alert formula"
        >
          {saveMutation.isPending ? "Saving…" : "Save Alert"}
        </button>
      </div>

      {/* Saved alerts */}
      <div>
        <h3 className="mb-2 text-xs font-medium text-gray-500">Saved Alerts</h3>
        {!savedData?.alerts?.length ? (
          <p className="text-xs text-gray-600">No saved alerts</p>
        ) : (
          <div className="space-y-1.5">
            {savedData.alerts.map((alert) => (
              <div
                key={alert.id}
                className="flex items-start justify-between gap-2 rounded border border-border/40 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium text-gray-200">{alert.name}</p>
                  <p className="mt-0.5 text-[10px] text-gray-500">
                    {alert.asset} • {alert.channel}
                  </p>
                  <code className="mt-0.5 text-[10px] text-accent/70 break-all">
                    {alert.formula}
                  </code>
                </div>
                <button
                  type="button"
                  onClick={() => { deleteMutation.mutate(alert.id); }}
                  disabled={deleteMutation.isPending}
                  className="shrink-0 text-[10px] text-gray-500 transition-colors hover:text-bearish"
                  aria-label={`Delete alert: ${alert.name}`}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
