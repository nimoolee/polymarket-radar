from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import settings
from .models import MonitorMarket


MAX_TRADABLE_ASK = 0.99
MAX_SPREAD = 0.03
UTC = timezone.utc


async def enrich_orderbooks(markets: list[MonitorMarket]) -> None:
    targets = [market for market in markets if market.status != "resolved" and market.clob_token_ids]
    targets = targets[: settings.clob_orderbook_check_limit]
    limits = httpx.Limits(max_connections=16, max_keepalive_connections=8)
    async with httpx.AsyncClient(timeout=8, limits=limits) as client:
        await asyncio.gather(*(enrich_market_orderbook(client, market) for market in targets), return_exceptions=True)


async def enrich_market_orderbook(client: httpx.AsyncClient, market: MonitorMarket) -> None:
    token = _leading_token(market)
    if not token:
        return
    response = await client.get(f"{settings.clob_api_url.rstrip('/')}/book", params={"token_id": token})
    response.raise_for_status()
    book = response.json()
    best_bid = _best_bid(book.get("bids"))
    best_ask = _best_ask(book.get("asks"))
    bid_depth = _depth(book.get("bids"), best_bid)
    ask_depth = _depth(book.get("asks"), best_ask)
    market.clob_best_bid = best_bid
    market.clob_best_ask = best_ask
    market.clob_depth = min(bid_depth, ask_depth) if bid_depth and ask_depth else 0
    market.clob_spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None
    market.orderbook_updated_at = datetime.now(UTC)
    market.tradable = bool(
        best_bid is not None
        and best_ask is not None
        and market.clob_spread is not None
        and market.clob_spread <= MAX_SPREAD
        and best_ask < MAX_TRADABLE_ASK
        and market.clob_depth >= 5
    )
    if best_bid is not None or best_ask is not None:
        market.best_bid = best_bid
        market.best_ask = best_ask
        market.clob_probability = best_ask if best_ask is not None else best_bid
        market.last_price = market.clob_probability
        if market.gamma_probability is not None and market.clob_probability is not None:
            market.gamma_clob_diff = market.clob_probability - market.gamma_probability
        market.price_source = "clob_orderbook"


def _leading_token(market: MonitorMarket) -> str | None:
    if not market.clob_token_ids:
        return None
    if market.outcomePrices:
        index = max(range(len(market.outcomePrices)), key=market.outcomePrices.__getitem__)
        if index < len(market.clob_token_ids):
            return market.clob_token_ids[index]
    return market.clob_token_ids[0]


def _best_bid(rows: Any) -> float | None:
    prices = _prices(rows)
    return max(prices) if prices else None


def _best_ask(rows: Any) -> float | None:
    prices = _prices(rows)
    if not prices:
        return None
    return min(prices)


def _prices(rows: Any) -> list[float]:
    prices: list[float] = []
    if not isinstance(rows, list):
        return prices
    for row in rows:
        try:
            prices.append(float(row["price"]))
        except (KeyError, TypeError, ValueError):
            continue
    return prices


def _depth(rows: Any, price: float | None) -> float:
    if price is None or not isinstance(rows, list):
        return 0
    total = 0.0
    for row in rows:
        try:
            if float(row["price"]) == price:
                total += float(row.get("size") or 0)
        except (KeyError, TypeError, ValueError):
            continue
    return total
