"""Backtesting endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/backtest", tags=["backtest"])
