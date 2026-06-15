"""Smart Money Flow Index — separates institutional vs retail buying pressure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)

# UTC hours considered institutional (London open + NY session)
INSTITUTIONAL_HOURS: list[int] = list(range(8, 11)) + list(range(13, 17))
# UTC hours considered retail (late Asia / post-NY)
RETAIL_HOURS: list[int] = list(range(0, 6)) + list(range(21, 24))


@dataclass
class SmartMoneyFlowResult:
    """Result of the smart money flow analysis for a symbol."""

    symbol: str
    smart_money_bias: float          # -1.0 (pure distribution) to +1.0 (pure accumulation)
    institutional_buy_ratio: float   # fraction of buys during institutional hours
    retail_buy_ratio: float          # fraction of buys during retail hours
    signal: str                      # "INSTITUTIONAL_ACCUMULATION", "RETAIL_FOMO",
                                     # "SMART_DISTRIBUTION", or "NEUTRAL"
    confidence: float
    description: str


class SmartMoneyFlowIndex:
    """Separate volume/buy pressure during institutional hours vs retail hours.

    Institutional hours (UTC): 08:00–10:59 (London open) + 13:00–16:59 (NY open).
    Retail hours (UTC):        00:00–05:59 (Asia night) + 21:00–23:59 (after NY).

    Signals:
    - INSTITUTIONAL_ACCUMULATION: high institutional buy ratio + low/falling retail
      buy ratio → smart money quietly building positions → BULLISH.
    - RETAIL_FOMO: high retail buy ratio + declining institutional buy ratio
      → late retail chasing → fade opportunity (BEARISH lean).
    - SMART_DISTRIBUTION: institutional sell (low buy ratio) + retail buying
      → classic distribution → BEARISH.
    - NEUTRAL: no clear divergence between institutional and retail flow.
    """

    STRONG_BIAS: float = 0.65  # institutional buy ratio above this = strong signal
    MIN_CANDLES_PER_BUCKET: int = 5  # need at least this many candles in each bucket

    def analyze(self, symbol: str, df: pd.DataFrame) -> SmartMoneyFlowResult:
        """Analyse smart money flow for the given OHLCV DataFrame.

        The DataFrame must have a DatetimeIndex in UTC (or a 'timestamp' column
        that is UTC-aware). Volume split uses the same CVD heuristic as cvd_calculator:
        bullish candle = all volume is buy; bearish = all sell; doji = 50/50.

        Args:
            symbol: Trading pair name.
            df: OHLCV DataFrame with DatetimeIndex (UTC) or 'timestamp' column.

        Returns:
            SmartMoneyFlowResult.
        """
        df = self._ensure_datetime_index(df)

        if df is None or len(df) < self.MIN_CANDLES_PER_BUCKET * 2:
            logger.debug("smart_money_flow: insufficient data for %s", symbol)
            return SmartMoneyFlowResult(
                symbol=symbol,
                smart_money_bias=0.0,
                institutional_buy_ratio=0.5,
                retail_buy_ratio=0.5,
                signal="NEUTRAL",
                confidence=0.0,
                description="Insufficient data for analysis.",
            )

        inst_buy = self._buy_ratio_for_hours(df, INSTITUTIONAL_HOURS)
        retail_buy = self._buy_ratio_for_hours(df, RETAIL_HOURS)

        # smart_money_bias: positive when institutions buy more than retail
        smart_money_bias = round(inst_buy - retail_buy, 4)

        signal, confidence = self._classify_signal(inst_buy, retail_buy)

        description = (
            f"Institutional buy ratio: {inst_buy:.2%} | "
            f"Retail buy ratio: {retail_buy:.2%} | "
            f"Bias: {smart_money_bias:+.3f}"
        )

        logger.info(
            "smart_money_flow: %s signal=%s inst=%.2f retail=%.2f conf=%.1f",
            symbol,
            signal,
            inst_buy,
            retail_buy,
            confidence,
        )

        return SmartMoneyFlowResult(
            symbol=symbol,
            smart_money_bias=smart_money_bias,
            institutional_buy_ratio=round(inst_buy, 4),
            retail_buy_ratio=round(retail_buy, 4),
            signal=signal,
            confidence=round(confidence, 1),
            description=description,
        )

    def _buy_ratio_for_hours(self, df: pd.DataFrame, hours: list[int]) -> float:
        """Calculate the average buy ratio (0-1) for rows falling in the specified UTC hours.

        Buy ratio per candle:
        - Bullish candle (close > open): 1.0 (all volume is buy).
        - Bearish candle (close < open): 0.0 (all volume is sell).
        - Doji: 0.5.

        The method returns the volume-weighted average buy ratio across all
        matching candles. If no candles fall in the specified hours, returns 0.5
        (neutral fallback).

        Args:
            df: OHLCV DataFrame with DatetimeIndex.
            hours: List of UTC hours (0-23) to filter on.

        Returns:
            Volume-weighted buy ratio between 0.0 and 1.0.
        """
        hour_mask = df.index.hour.isin(hours)
        bucket = df[hour_mask]

        if len(bucket) < self.MIN_CANDLES_PER_BUCKET:
            return 0.5  # insufficient data → neutral

        opens = bucket["open"].values
        closes = bucket["close"].values
        volumes = bucket["volume"].values

        # Per-candle buy ratio
        buy_ratios = np.where(
            closes > opens,
            1.0,
            np.where(closes < opens, 0.0, 0.5),
        )

        # Volume-weighted average
        total_vol = volumes.sum()
        if total_vol <= 0:
            return float(buy_ratios.mean())

        weighted = float((buy_ratios * volumes).sum() / total_vol)
        return float(np.clip(weighted, 0.0, 1.0))

    def _classify_signal(
        self, inst_buy: float, retail_buy: float
    ) -> tuple[str, float]:
        """Classify the flow pattern and return (signal, confidence).

        Classification logic:
        - INSTITUTIONAL_ACCUMULATION: inst_buy >= STRONG_BIAS and
          retail_buy < inst_buy - 0.10 (retail clearly lagging).
        - SMART_DISTRIBUTION: inst_buy < (1 - STRONG_BIAS) and
          retail_buy > inst_buy + 0.10 (retail buying while institutions sell).
        - RETAIL_FOMO: retail_buy >= STRONG_BIAS and inst_buy < 0.55
          (retail surging, institutions not participating).
        - NEUTRAL: no clear pattern.

        Confidence scales with the magnitude of divergence between the two buckets.

        Args:
            inst_buy: Institutional buy ratio (0-1).
            retail_buy: Retail buy ratio (0-1).

        Returns:
            Tuple of (signal_name, confidence_pct).
        """
        divergence = inst_buy - retail_buy  # positive = institutions buying more

        if inst_buy >= self.STRONG_BIAS and retail_buy < inst_buy - 0.10:
            signal = "INSTITUTIONAL_ACCUMULATION"
            # Confidence scales from 60% at STRONG_BIAS to 90% at 90% buy ratio
            conf = 60.0 + (inst_buy - self.STRONG_BIAS) / (1.0 - self.STRONG_BIAS) * 30.0

        elif inst_buy < (1.0 - self.STRONG_BIAS) and retail_buy > inst_buy + 0.10:
            signal = "SMART_DISTRIBUTION"
            # Confidence scales with how much institutions are NOT buying
            conf = 60.0 + ((1.0 - self.STRONG_BIAS) - inst_buy) / (1.0 - self.STRONG_BIAS) * 30.0

        elif retail_buy >= self.STRONG_BIAS and inst_buy < 0.55:
            signal = "RETAIL_FOMO"
            conf = 55.0 + (retail_buy - self.STRONG_BIAS) / (1.0 - self.STRONG_BIAS) * 25.0

        else:
            signal = "NEUTRAL"
            conf = max(0.0, 50.0 - abs(divergence) * 20.0)

        return signal, round(min(conf, 90.0), 1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_datetime_index(self, df: pd.DataFrame) -> pd.DataFrame | None:
        """Ensure the DataFrame has a UTC-aware DatetimeIndex.

        Accepts:
        - DataFrame already with DatetimeIndex (tz-aware or naive UTC).
        - DataFrame with a 'timestamp' column (int ms, float, or datetime str).

        Returns:
            DataFrame with DatetimeIndex in UTC, or None if conversion failed.
        """
        if df is None:
            return None

        df = df.copy()

        if isinstance(df.index, pd.DatetimeIndex):
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            return df

        # Try to build from a 'timestamp' column
        if "timestamp" in df.columns:
            ts_col = df["timestamp"]
            sample = ts_col.dropna().iloc[0] if not ts_col.dropna().empty else None

            if sample is None:
                return None

            if isinstance(sample, (int, float)):
                # Assume milliseconds if value > 1e10, else seconds
                unit = "ms" if float(sample) > 1e10 else "s"
                df.index = pd.to_datetime(ts_col, unit=unit, utc=True)
            elif isinstance(sample, str):
                df.index = pd.to_datetime(ts_col, utc=True)
            elif isinstance(sample, datetime):
                df.index = pd.DatetimeIndex(ts_col).tz_localize("UTC")
            else:
                return None

            return df

        # Last resort: try to convert the existing index
        try:
            df.index = pd.to_datetime(df.index, utc=True)
            return df
        except Exception:
            logger.warning("smart_money_flow: cannot convert index to datetime")
            return None
