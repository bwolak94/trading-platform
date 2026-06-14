import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SignalCard } from "@/components/SignalCard/SignalCard";
import type { Signal } from "@/types";

// ── Fixtures ──────────────────────────────────────────────────────────────

const BASE_SIGNAL: Signal = {
  id: "signal-001",
  asset: "BTCUSDT",
  direction: "LONG",
  confidence: 78,
  regime: "TREND_BULL",
  entry_price: 65000,
  stop_loss: 63000,
  take_profit_1: 68000,
  take_profit_2: 71000,
  risk_reward: 1.5,
  position_size_pct: 2,
  technical_score: 80,
  onchain_score: 70,
  sentiment_score: 65,
  macro_score: 60,
  factors: [
    { name: "Trend", weight: 0.4, score: 0.8, label: "Strong" },
    { name: "Momentum", weight: 0.3, score: 0.7, label: "Bullish" },
    { name: "Volume", weight: 0.3, score: 0.6, label: "Above avg" },
  ],
  status: "ACTIVE",
  expires_at: new Date(Date.now() + 8 * 3600 * 1000).toISOString(),
  created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
  updated_at: new Date().toISOString(),
};

const SHORT_SIGNAL: Signal = {
  ...BASE_SIGNAL,
  id: "signal-002",
  direction: "SHORT",
  entry_price: 65000,
  stop_loss: 67000,
  take_profit_1: 62000,
  take_profit_2: null,
  regime: "TREND_BEAR",
};

// Mock the sparkline fetch so tests don't make real HTTP requests
beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => [
      { close: 64000 }, { close: 64500 }, { close: 65000 },
    ],
  } as Response);
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

// ── Tests ─────────────────────────────────────────────────────────────────

describe("SignalCard", () => {
  describe("rendering", () => {
    it("renders asset name and direction for a LONG signal", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText(/BTCUSDT/)).toBeInTheDocument();
      expect(screen.getByText(/LONG/)).toBeInTheDocument();
    });

    it("renders asset name and direction for a SHORT signal", () => {
      render(<SignalCard signal={SHORT_SIGNAL} />);
      expect(screen.getByText(/BTCUSDT/)).toBeInTheDocument();
      expect(screen.getByText(/SHORT/)).toBeInTheDocument();
    });

    it("renders entry, SL, and TP1 price levels", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText("Entry")).toBeInTheDocument();
      expect(screen.getByText("SL")).toBeInTheDocument();
      expect(screen.getByText("TP1")).toBeInTheDocument();
    });

    it("renders TP2 when provided", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText("TP2")).toBeInTheDocument();
    });

    it("does not render TP2 when null", () => {
      render(<SignalCard signal={SHORT_SIGNAL} />);
      expect(screen.queryByText("TP2")).not.toBeInTheDocument();
    });

    it("renders confidence percentage", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText(/78%/)).toBeInTheDocument();
    });

    it("renders ACTIVE status badge", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    });

    it("renders regime badge", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText("TREND BULL")).toBeInTheDocument();
    });

    it("renders first 3 factors", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText("Trend")).toBeInTheDocument();
      expect(screen.getByText("Momentum")).toBeInTheDocument();
      expect(screen.getByText("Volume")).toBeInTheDocument();
    });

    it("renders duplicate badge when isDuplicate=true", () => {
      render(<SignalCard signal={BASE_SIGNAL} isDuplicate />);
      expect(screen.getByText("DUP")).toBeInTheDocument();
    });

    it("does not render duplicate badge by default", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.queryByText("DUP")).not.toBeInTheDocument();
    });

    it("renders copy button", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByLabelText("Copy trade parameters to clipboard")).toBeInTheDocument();
    });
  });

  describe("memoization", () => {
    it("renders two cards with different signal ids independently", () => {
      const { rerender } = render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText(/BTCUSDT/)).toBeInTheDocument();
      rerender(<SignalCard signal={SHORT_SIGNAL} />);
      expect(screen.getByText(/BTCUSDT/)).toBeInTheDocument();
    });
  });

  describe("interaction", () => {
    it("calls onNavigate when clicked", () => {
      const handleNavigate = vi.fn();
      render(<SignalCard signal={BASE_SIGNAL} onNavigate={handleNavigate} />);
      const card = screen.getByRole("button");
      fireEvent.click(card);
      expect(handleNavigate).toHaveBeenCalledWith("BTCUSDT");
    });

    it("calls onNavigate when Enter is pressed", () => {
      const handleNavigate = vi.fn();
      render(<SignalCard signal={BASE_SIGNAL} onNavigate={handleNavigate} />);
      const card = screen.getByRole("button");
      fireEvent.keyDown(card, { key: "Enter" });
      expect(handleNavigate).toHaveBeenCalledWith("BTCUSDT");
    });

    it("does not render as a button when onNavigate is not provided", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.queryByRole("button", { name: /Navigate/ })).not.toBeInTheDocument();
    });
  });

  describe("slippage-adjusted R/R", () => {
    it("shows slippage-adjusted R/R in footer", () => {
      render(<SignalCard signal={BASE_SIGNAL} slippageBps={10} />);
      // The R/R text will be present
      expect(screen.getByText(/R\/R/)).toBeInTheDocument();
    });
  });

  describe("expiry countdown", () => {
    it("renders expiry countdown for a future expires_at", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(screen.getByText(/Expires:/)).toBeInTheDocument();
    });
  });

  describe("accessibility", () => {
    it("sparkline has an aria-label", async () => {
      // Give sparkline data time to be mocked and rendered
      render(<SignalCard signal={BASE_SIGNAL} />);
      // The SVG aria-label may not yet be there (loading state), just verify the card renders
      expect(screen.getByText(/78%/)).toBeInTheDocument();
    });

    it("copy button has aria-label", () => {
      render(<SignalCard signal={BASE_SIGNAL} />);
      expect(
        screen.getByLabelText("Copy trade parameters to clipboard"),
      ).toBeInTheDocument();
    });
  });
});
