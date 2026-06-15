import { describe, it, expect } from "vitest";

// ── format.ts ─────────────────────────────────────────────────────────────

import {
  fmtPrice,
  fmtUSD,
  fmtPct,
  fmtNumber,
  fmtRatio,
  colorClass,
} from "@/lib/format";

describe("fmtPrice", () => {
  it("formats a large price with 2 decimal places and comma separator", () => {
    expect(fmtPrice(65000)).toBe("$65,000.00");
  });

  it("formats a price between 1 and 999 with up to 4 decimals", () => {
    const result = fmtPrice(1.5);
    expect(result).toMatch(/^\$1\.\d{2,4}$/);
  });

  it("formats a sub-1 price with toPrecision(4)", () => {
    expect(fmtPrice(0.0004567)).toBe("$0.0004567");
  });

  it("returns em dash for null", () => {
    expect(fmtPrice(null)).toBe("—");
  });

  it("returns em dash for undefined", () => {
    expect(fmtPrice(undefined)).toBe("—");
  });

  it("returns em dash for Infinity", () => {
    expect(fmtPrice(Infinity)).toBe("—");
  });
});

describe("fmtUSD", () => {
  it("formats values under 1000 with dollar sign", () => {
    expect(fmtUSD(500)).toBe("$500.00");
  });

  it("formats thousands as K", () => {
    expect(fmtUSD(5000)).toBe("$5.0K");
  });

  it("formats millions as M", () => {
    expect(fmtUSD(2_500_000)).toBe("$2.5M");
  });

  it("formats billions as B", () => {
    expect(fmtUSD(1_200_000_000)).toBe("$1.2B");
  });

  it("handles negative values with minus prefix", () => {
    expect(fmtUSD(-3000)).toBe("-$3.0K");
  });

  it("returns em dash for null", () => {
    expect(fmtUSD(null)).toBe("—");
  });
});

describe("fmtPct", () => {
  it("formats a positive percentage with 2 decimals by default", () => {
    expect(fmtPct(12.5)).toBe("12.50%");
  });

  it("formats a negative percentage", () => {
    expect(fmtPct(-3.14)).toBe("-3.14%");
  });

  it("formats zero as 0.00%", () => {
    expect(fmtPct(0)).toBe("0.00%");
  });

  it("adds + sign when showSign=true and value is positive", () => {
    expect(fmtPct(5, { showSign: true })).toBe("+5.00%");
  });

  it("does not add + sign for negative with showSign=true", () => {
    expect(fmtPct(-5, { showSign: true })).toBe("-5.00%");
  });

  it("respects custom decimals", () => {
    expect(fmtPct(12.5, { decimals: 0 })).toBe("13%");
  });

  it("returns em dash for null", () => {
    expect(fmtPct(null)).toBe("—");
  });
});

describe("fmtNumber", () => {
  it("formats a number with 2 decimal places by default", () => {
    expect(fmtNumber(1234.567)).toBe("1234.57");
  });

  it("respects custom decimal places", () => {
    expect(fmtNumber(1234.567, { decimals: 0 })).toBe("1235");
  });

  it("formats in compact mode — K for thousands", () => {
    expect(fmtNumber(5500, { compact: true })).toBe("5.5K");
  });

  it("formats in compact mode — M for millions", () => {
    expect(fmtNumber(3_200_000, { compact: true })).toBe("3.2M");
  });

  it("returns em dash for null", () => {
    expect(fmtNumber(null)).toBe("—");
  });
});

describe("fmtRatio", () => {
  it("formats ratio with one decimal and x suffix", () => {
    expect(fmtRatio(1.5)).toBe("1.5x");
  });

  it("formats zero ratio", () => {
    expect(fmtRatio(0)).toBe("0.0x");
  });

  it("returns em dash for null", () => {
    expect(fmtRatio(null)).toBe("—");
  });
});

describe("colorClass", () => {
  it("returns text-bullish for positive values", () => {
    expect(colorClass(10)).toBe("text-bullish");
  });

  it("returns text-bearish for negative values", () => {
    expect(colorClass(-10)).toBe("text-bearish");
  });

  it("returns neutral class for zero", () => {
    expect(colorClass(0)).toBe("text-gray-400");
  });

  it("returns neutral class for null", () => {
    expect(colorClass(null)).toBe("text-gray-400");
  });

  it("respects a custom neutral class", () => {
    expect(colorClass(0, "text-white")).toBe("text-white");
  });
});

// ── validation.ts ─────────────────────────────────────────────────────────

import {
  backtestFormSchema,
  settingsFormSchema,
  alertFormSchema,
} from "@/lib/validation";

describe("backtestFormSchema", () => {
  const valid = {
    strategy: "TrendFollowing",
    asset: "BTCUSDT",
    timeframe: "1h" as const,
    start_date: "2024-01-01",
    end_date: "2024-12-31",
    initial_capital: 10000,
    risk_per_trade_pct: 1,
  };

  it("accepts valid backtest form data", () => {
    expect(backtestFormSchema.safeParse(valid).success).toBe(true);
  });

  it("rejects empty strategy", () => {
    expect(
      backtestFormSchema.safeParse({ ...valid, strategy: "" }).success,
    ).toBe(false);
  });

  it("rejects invalid timeframe", () => {
    expect(
      backtestFormSchema.safeParse({ ...valid, timeframe: "99h" }).success,
    ).toBe(false);
  });

  it("rejects zero initial capital", () => {
    expect(
      backtestFormSchema.safeParse({ ...valid, initial_capital: 0 }).success,
    ).toBe(false);
  });

  it("rejects end_date before start_date", () => {
    expect(
      backtestFormSchema.safeParse({
        ...valid,
        start_date: "2024-12-01",
        end_date: "2024-01-01",
      }).success,
    ).toBe(false);
  });

  it("rejects risk_per_trade_pct above 100", () => {
    expect(
      backtestFormSchema.safeParse({ ...valid, risk_per_trade_pct: 101 }).success,
    ).toBe(false);
  });
});

describe("settingsFormSchema", () => {
  const valid = {
    capital: 10000,
    risk_per_trade_pct: 1,
    max_drawdown_pct: 10,
    telegram_chat_id: null,
    notifications_enabled: true,
    enabled_assets: ["BTCUSDT"],
  };

  it("accepts valid settings", () => {
    expect(settingsFormSchema.safeParse(valid).success).toBe(true);
  });

  it("accepts null capital", () => {
    expect(
      settingsFormSchema.safeParse({ ...valid, capital: null }).success,
    ).toBe(true);
  });

  it("rejects risk above 10%", () => {
    expect(
      settingsFormSchema.safeParse({ ...valid, risk_per_trade_pct: 11 }).success,
    ).toBe(false);
  });

  it("rejects max_drawdown above 50%", () => {
    expect(
      settingsFormSchema.safeParse({ ...valid, max_drawdown_pct: 51 }).success,
    ).toBe(false);
  });

  it("rejects empty enabled_assets array", () => {
    expect(
      settingsFormSchema.safeParse({ ...valid, enabled_assets: [] }).success,
    ).toBe(false);
  });
});

describe("alertFormSchema", () => {
  it("accepts valid alert data", () => {
    const valid = { asset: "BTCUSDT", condition: "above" as const, value: 70000 };
    expect(alertFormSchema.safeParse(valid).success).toBe(true);
  });

  it("rejects zero value", () => {
    expect(
      alertFormSchema.safeParse({ asset: "BTCUSDT", condition: "above", value: 0 }).success,
    ).toBe(false);
  });

  it("rejects invalid condition", () => {
    expect(
      alertFormSchema.safeParse({ asset: "BTCUSDT", condition: "equals", value: 50000 }).success,
    ).toBe(false);
  });

  it("rejects empty asset", () => {
    expect(
      alertFormSchema.safeParse({ asset: "", condition: "above", value: 50000 }).success,
    ).toBe(false);
  });
});
