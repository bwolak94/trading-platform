-- Migration: 20250427120000_brin_indexes.sql
-- Purpose: Add BRIN indexes on time-ordered columns for efficient range scans.
-- BRIN (Block Range INdex) is ideal for naturally ordered time-series data
-- like OHLCV candles and signals — tiny index size, fast sequential scans.
-- Note: Renamed from 20260426120000 (future date) to correct timestamp.

-- market_data.timestamp — primary time-range scan column
create index if not exists idx_market_data_timestamp_brin
  on market_data using brin (timestamp);

-- signals.created_at — used by /signals with date-range filters
create index if not exists idx_signals_created_at_brin
  on signals using brin (created_at);

-- signals.updated_at — used by status-check queries
create index if not exists idx_signals_updated_at_brin
  on signals using brin (updated_at);

-- simulated_positions.opened_at / closed_at — session P&L and attribution queries
create index if not exists idx_simulated_positions_opened_at_brin
  on simulated_positions using brin (opened_at);

create index if not exists idx_simulated_positions_closed_at_brin
  on simulated_positions using brin (closed_at);

-- sentiment_data.period_start — sentiment history range queries
create index if not exists idx_sentiment_data_period_start_brin
  on sentiment_data using brin (period_start);
