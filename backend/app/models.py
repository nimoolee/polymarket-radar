from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


MarketKind = Literal["sports", "esports", "crypto", "general"]
MarketStatus = Literal["active", "ending", "resolved"]


class MonitorMarket(BaseModel):
    market_id: str
    clob_token_ids: List[str] = Field(default_factory=list)
    endDate: Optional[datetime] = None
    real_deadline: Optional[datetime] = None
    time_basis: str = "endDate"
    rules: Optional[str] = None
    active: bool = True
    closed: bool = False
    question: str
    outcomePrices: List[float] = Field(default_factory=list)
    gamma_probability: Optional[float] = None
    clob_probability: Optional[float] = None
    gamma_clob_diff: Optional[float] = None
    outcomes: List[str] = Field(default_factory=list)
    leading_outcome: Optional[str] = None
    game_start_time: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    market_url: Optional[str] = None
    image: Optional[str] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    category: Optional[str] = None
    kind: MarketKind
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    clob_best_bid: Optional[float] = None
    clob_best_ask: Optional[float] = None
    clob_spread: Optional[float] = None
    clob_depth: Optional[float] = None
    orderbook_updated_at: Optional[datetime] = None
    tradable: Optional[bool] = None
    price_source: str = "gamma"
    last_price: Optional[float] = None
    last_trade_price: Optional[float] = None
    last_trade_at: Optional[datetime] = None
    price_change_30s: Optional[float] = None
    price_change_3m: Optional[float] = None
    status_tags: List[str] = Field(default_factory=list)
    score: float = 0
    status: MarketStatus = "active"
    updated_at: datetime


class PricePoint(BaseModel):
    market_id: str
    price: float
    at: datetime


class PushEvent(BaseModel):
    id: str
    market_id: str
    question: str
    price: Optional[float] = None
    remaining_seconds: Optional[int] = None
    reason: str
    created_at: datetime


class ClientPayload(BaseModel):
    type: str
    data: Any
