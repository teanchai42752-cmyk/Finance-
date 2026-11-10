import hmac
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("MT5_DB_PATH", str(BASE_DIR / "mt5_bridge.db")))
API_TOKEN = os.getenv("MT5_API_TOKEN", "")
app = FastAPI(title="MT5 Market Data Bridge", version="1.0.0")


class Bar(BaseModel):
    time: int = Field(gt=0)
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = Field(ge=0)


class MarketPayload(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(min_length=1, max_length=8)
    bid: float
    ask: float
    timestamp_utc: int = Field(gt=0)
    bars: List[Bar] = Field(min_length=1, max_length=2000)


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


@app.on_event("startup")
def startup():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS market_bars (
            symbol TEXT NOT NULL, timeframe TEXT NOT NULL, bar_time INTEGER NOT NULL,
            open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
            tick_volume INTEGER NOT NULL, received_at TEXT NOT NULL,
            PRIMARY KEY(symbol, timeframe, bar_time))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS market_ticks (
            symbol TEXT NOT NULL, timeframe TEXT NOT NULL, bid REAL NOT NULL, ask REAL NOT NULL,
            timestamp_utc INTEGER NOT NULL, received_at TEXT NOT NULL,
            PRIMARY KEY(symbol, timeframe))""")


def check_token(authorization: str | None):
    if not API_TOKEN:
        raise HTTPException(status_code=503, detail="MT5_API_TOKEN is not configured on server")
    if not hmac.compare_digest(authorization or "", "Bearer " + API_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid API token")


@app.get("/health")
def health():
    return {"status": "ok", "service": "mt5-market-data-bridge"}


@app.post("/api/v1/ingest")
def ingest(payload: MarketPayload, authorization: str | None = Header(default=None)):
    check_token(authorization)
    now = datetime.now(timezone.utc).isoformat()
    symbol, timeframe = payload.symbol.upper(), payload.timeframe.upper()
    with connect_db() as conn:
        conn.executemany("""INSERT INTO market_bars
            (symbol,timeframe,bar_time,open,high,low,close,tick_volume,received_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol,timeframe,bar_time) DO UPDATE SET
            open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,
            tick_volume=excluded.tick_volume,received_at=excluded.received_at""",
            [(symbol,timeframe,b.time,b.open,b.high,b.low,b.close,b.tick_volume,now) for b in payload.bars])
        conn.execute("""INSERT INTO market_ticks
            (symbol,timeframe,bid,ask,timestamp_utc,received_at) VALUES (?,?,?,?,?,?)
            ON CONFLICT(symbol,timeframe) DO UPDATE SET bid=excluded.bid,ask=excluded.ask,
            timestamp_utc=excluded.timestamp_utc,received_at=excluded.received_at""",
            (symbol,timeframe,payload.bid,payload.ask,payload.timestamp_utc,now))
        conn.execute("""DELETE FROM market_bars WHERE symbol=? AND timeframe=? AND bar_time NOT IN
            (SELECT bar_time FROM market_bars WHERE symbol=? AND timeframe=? ORDER BY bar_time DESC LIMIT 2000)""",
            (symbol,timeframe,symbol,timeframe))
    return {"accepted": len(payload.bars), "symbol": symbol, "timeframe": timeframe, "received_at": now}


@app.get("/api/v1/market-data")
def market_data(symbol: str = Query(min_length=1, max_length=32),
                timeframe: str = Query(min_length=1, max_length=8),
                limit: int = Query(default=500, ge=20, le=2000),
                authorization: str | None = Header(default=None)):
    check_token(authorization)
    symbol, timeframe = symbol.upper(), timeframe.upper()
    with connect_db() as conn:
        tick = conn.execute("SELECT bid,ask,timestamp_utc,received_at FROM market_ticks WHERE symbol=? AND timeframe=?",
                            (symbol,timeframe)).fetchone()
        bars = conn.execute("SELECT bar_time,open,high,low,close,tick_volume FROM market_bars WHERE symbol=? AND timeframe=? ORDER BY bar_time DESC LIMIT ?",
                            (symbol,timeframe,limit)).fetchall()
    if tick is None or not bars:
        raise HTTPException(status_code=404, detail="No MT5 data received for this symbol/timeframe yet")
    return {
        "symbol": symbol, "timeframe": timeframe, "bid": tick["bid"], "ask": tick["ask"],
        "timestamp_utc": tick["timestamp_utc"], "received_at": tick["received_at"],
        "bars": [{"time": r["bar_time"], "open": r["open"], "high": r["high"], "low": r["low"],
                  "close": r["close"], "tick_volume": r["tick_volume"]} for r in reversed(bars)]
    }
