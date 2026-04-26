-- Migration: add composite indexes on market_data and signals tables
-- Affected tables: market_data, signals, simulated_position
-- Purpose: critical query paths hit these columns repeatedly under load;
--          without these indexes, range scans degrade to full-table reads.

-- market_data: the primary OHLCV query pattern (asset + timeframe + timestamp range)
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_market_data_asset_tf_ts
  ON market_data (asset, timeframe, timestamp DESC);

-- signals: active-signal lookups and feed queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_signals_status_created
  ON signals (status, created_at DESC);

-- signals: per-asset history queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_signals_asset_status
  ON signals (asset, status, created_at DESC);

-- signals: expiry cleanup scan (daily task)
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_signals_expires_at
  ON signals (expires_at)
  WHERE expires_at IS NOT NULL;

-- simulated_position: open position lookups (used every 15s by simulation engine)
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_simpos_status_opened
  ON simulated_position (status, opened_at DESC);

-- simulated_position: closed trade analytics (benchmark, attribution, MAE)
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_simpos_closed_at
  ON simulated_position (closed_at DESC)
  WHERE status != 'OPEN';

-- sentiment_data: latest-per-asset lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_sentiment_asset_created
  ON sentiment_data (asset, created_at DESC);

-- market_regime: current regime per asset
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_regime_asset_started
  ON market_regime (asset, started_at DESC)
  WHERE ended_at IS NULL;
