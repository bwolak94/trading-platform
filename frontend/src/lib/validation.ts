import { z } from "zod";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1D", "1W"] as const;

/** Schema for backtest form submission */
export const backtestFormSchema = z
  .object({
    strategy: z.string().min(1, { error: "Strategy is required" }),
    asset: z.string().min(1, { error: "Asset is required" }),
    timeframe: z.enum(TIMEFRAMES, {
      error: "Invalid timeframe",
    }),
    start_date: z.string().min(1, { error: "Start date is required" }),
    end_date: z.string().min(1, { error: "End date is required" }),
    initial_capital: z
      .number({ error: "Capital must be a number" })
      .positive({ error: "Capital must be positive" }),
    risk_per_trade_pct: z
      .number({ error: "Risk % must be a number" })
      .min(0.1, { error: "Risk must be at least 0.1%" })
      .max(100, { error: "Risk cannot exceed 100%" }),
  })
  .refine((data) => new Date(data.end_date) > new Date(data.start_date), {
    error: "End date must be after start date",
    path: ["end_date"],
  });

/** Schema for settings form submission */
export const settingsFormSchema = z.object({
  capital: z
    .number({ error: "Capital must be a number" })
    .min(0, { error: "Capital cannot be negative" })
    .nullable(),
  risk_per_trade_pct: z
    .number({ error: "Risk % must be a number" })
    .min(0.1, { error: "Risk must be at least 0.1%" })
    .max(10, { error: "Risk cannot exceed 10%" }),
  max_drawdown_pct: z
    .number({ error: "Max drawdown must be a number" })
    .min(1, { error: "Max drawdown must be at least 1%" })
    .max(50, { error: "Max drawdown cannot exceed 50%" }),
  telegram_chat_id: z.string().nullable(),
  notifications_enabled: z.boolean(),
  enabled_assets: z
    .array(z.string().min(1))
    .min(1, { error: "At least one asset must be enabled" }),
});

/** Schema for alert form submission */
export const alertFormSchema = z.object({
  asset: z.string().min(1, { error: "Asset is required" }),
  condition: z.enum(["above", "below", "crosses"] as const, {
    error: "Invalid condition",
  }),
  value: z
    .number({ error: "Value must be a number" })
    .positive({ error: "Value must be positive" }),
});

/** Inferred types from schemas */
export type BacktestFormData = z.infer<typeof backtestFormSchema>;
export type SettingsFormData = z.infer<typeof settingsFormSchema>;
export type AlertFormData = z.infer<typeof alertFormSchema>;
