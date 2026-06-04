from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import websockets

from .config import settings
from .hub import manager
from .models import MonitorMarket, PushEvent

UTC = timezone.utc

class ClobMarketStream:
    def __init__(self) -> None:
        self._target_tokens: set[str] = set()
        self._token_to_market: dict[str, str] = {}
        self._token_to_outcome_index: dict[str, int] = {}
        self._markets: dict[str, MonitorMarket] = {}
        self._last_prices: dict[str, float] = {}
        self._price_history: dict[str, list[tuple[datetime, float]]] = {}
        self._focus_market_ids: set[str] = set()
        self._enabled = True
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()

    async def set_enabled(self, enabled: bool) -> None:
        async with self._lock:
            self._enabled = enabled
            if not enabled:
                self._target_tokens = set()
                self._token_to_market = {}
                self._token_to_outcome_index = {}
        if not enabled:
            await manager.broadcast("connection_status", {"clob": "paused"})

    async def sync_markets(self, markets: dict[str, MonitorMarket]) -> None:
        tokens = {token for market in markets.values() if market.status != "resolved" for token in market.clob_token_ids}
        token_to_market = {token: market.market_id for market in markets.values() for token in market.clob_token_ids}
        token_to_outcome_index = {
            token: index
            for market in markets.values()
            for index, token in enumerate(market.clob_token_ids)
        }
        async with self._lock:
            if not self._enabled:
                self._markets = {}
                self._target_tokens = set()
                self._token_to_market = {}
                self._token_to_outcome_index = {}
                return
            self._markets = markets.copy()
            self._target_tokens = tokens
            self._token_to_market = token_to_market
            self._token_to_outcome_index = token_to_outcome_index

    async def set_focus_markets(self, market_ids: list[str]) -> None:
        async with self._lock:
            self._focus_market_ids = {str(market_id) for market_id in market_ids if market_id}

    async def run(self) -> None:
        if settings.use_mock_data:
            await self._run_mock_stream()
        else:
            await self._run_real_stream()

    async def _run_mock_stream(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(2.5)
            async with self._lock:
                if not self._enabled:
                    continue
                markets = [market for market in self._markets.values() if market.status != "resolved"]
            if not markets:
                continue
            market = random.choice(markets)
            base = market.last_price or max(market.outcomePrices or [0.9])
            price = max(0.01, min(0.99, base + random.uniform(-0.012, 0.014)))
            token = market.clob_token_ids[0] if market.clob_token_ids else ""
            await self._handle_price_update(market.market_id, token, price, "best_bid_ask")

    async def _run_real_stream(self) -> None:
        backoff = 1
        while not self._stop.is_set():
            try:
                async with self._lock:
                    enabled = self._enabled
                if not enabled:
                    await manager.broadcast("connection_status", {"clob": "paused"})
                    await asyncio.sleep(2)
                    continue
                async with websockets.connect(settings.clob_ws_url, ping_interval=None, open_timeout=20) as ws:
                    backoff = 1
                    subscribed: set[str] = set()
                    ping_task = asyncio.create_task(self._send_heartbeat(ws))
                    await manager.broadcast("connection_status", {"clob": "connected"})
                    while not self._stop.is_set():
                        async with self._lock:
                            if not self._enabled:
                                break
                            desired = set(self._prioritized_tokens_locked()[: settings.clob_max_tokens])
                        to_sub = desired - subscribed
                        to_unsub = subscribed - desired
                        if to_sub:
                            payload = {
                                "assets_ids": sorted(to_sub),
                                "custom_feature_enabled": True,
                            }
                            if subscribed:
                                payload["operation"] = "subscribe"
                            else:
                                payload["type"] = "market"
                            await ws.send(json.dumps(payload))
                            subscribed.update(to_sub)
                        if to_unsub:
                            await ws.send(json.dumps({"operation": "unsubscribe", "assets_ids": sorted(to_unsub)}))
                            subscribed.difference_update(to_unsub)
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        except TimeoutError:
                            continue
                        await self._handle_ws_message(raw)
                    ping_task.cancel()
                    await asyncio.gather(ping_task, return_exceptions=True)
            except Exception as exc:
                if "ping_task" in locals():
                    ping_task.cancel()
                    await asyncio.gather(ping_task, return_exceptions=True)
                await manager.broadcast("connection_status", {"clob": "reconnecting", "error": str(exc)})
                await asyncio.sleep(min(backoff, 30))
                backoff *= 2

    def _prioritized_tokens_locked(self) -> list[str]:
        active_markets = [market for market in self._markets.values() if market.status != "resolved"]
        focus_tokens = [
            token
            for market in active_markets
            if market.market_id in self._focus_market_ids
            for token in market.clob_token_ids
        ]
        ranked_tokens = [
            token
            for market in sorted(active_markets, key=_clob_priority_key)
            for token in market.clob_token_ids
        ]
        seen: set[str] = set()
        ordered: list[str] = []
        for token in [*focus_tokens, *ranked_tokens]:
            if token and token not in seen:
                seen.add(token)
                ordered.append(token)
        return ordered

    async def _send_heartbeat(self, ws) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(10)
            await ws.send("PING")

    async def _handle_ws_message(self, raw: str | bytes) -> None:
        if raw in {"PONG", b"PONG", "ping", b"ping"}:
            await manager.broadcast("connection_status", {"clob": "connected"})
            return
        data = json.loads(raw)
        events = data if isinstance(data, list) else [data]
        for event in events:
            event_type = event.get("event_type") or event.get("type")
            token_id = str(event.get("asset_id") or event.get("token_id") or event.get("market"))
            async with self._lock:
                market_id = self._token_to_market.get(token_id)
            if event_type == "price_change":
                for change in event.get("price_changes", []):
                    change_token = str(change.get("asset_id"))
                    async with self._lock:
                        change_market_id = self._token_to_market.get(change_token)
                    price = _extract_live_price(change)
                    if price is not None and change_market_id:
                        await self._handle_price_update(change_market_id, change_token, price, event_type)
            elif event_type in {"best_bid_ask", "last_trade_price", "book"} and market_id:
                price = _extract_live_price(event)
                if price is not None:
                    await self._handle_price_update(market_id, token_id, price, event_type)
            elif event_type == "market_resolved" and market_id:
                await self._handle_resolved(market_id)

    async def _handle_price_update(self, market_id: str, token_id: str, price: float, event_type: str) -> None:
        previous = self._last_prices.get(market_id)
        now = datetime.now(UTC)
        await manager.broadcast("price_update", {"market_id": market_id, "token_id": token_id, "price": price, "event_type": event_type})

        async with self._lock:
            market = self._markets.get(market_id)
            outcome_index = self._token_to_outcome_index.get(token_id)
        if not market:
            return
        if outcome_index is not None and outcome_index < len(market.outcomePrices):
            market.outcomePrices[outcome_index] = price
        leading_index = None
        if market.outcomePrices:
            leading_index = max(range(len(market.outcomePrices)), key=market.outcomePrices.__getitem__)
            market.clob_probability = market.outcomePrices[leading_index]
            market.last_price = market.clob_probability
            market.leading_outcome = market.outcomes[leading_index] if leading_index < len(market.outcomes) else market.leading_outcome
        else:
            market.clob_probability = price
            market.last_price = price
        if market.gamma_probability is not None and market.clob_probability is not None:
            market.gamma_clob_diff = market.clob_probability - market.gamma_probability
        market.price_source = "clob_ws"
        if event_type == "last_trade_price" and (outcome_index is None or outcome_index == leading_index):
            market.last_trade_price = price
            market.last_trade_at = now
            if price >= (market.clob_probability or 0):
                market.clob_probability = price
                market.last_price = price
                if market.gamma_probability is not None:
                    market.gamma_clob_diff = market.clob_probability - market.gamma_probability
        if market.clob_probability is not None:
            self._last_prices[market_id] = market.clob_probability
            history = self._price_history.setdefault(market_id, [])
            history.append((now, market.clob_probability))
            self._price_history[market_id] = [(at, value) for at, value in history if now - at <= timedelta(minutes=4)]
        market.price_change_30s = _change_since(self._price_history.get(market_id, []), now, 30)
        market.price_change_3m = _change_since(self._price_history.get(market_id, []), now, 180)
        market.tradable = None
        remaining = int(((market.real_deadline or market.endDate) - now).total_seconds()) if (market.real_deadline or market.endDate) else None
        if _should_push(market, now):
            await manager.broadcast(
                "push_event",
                PushEvent(
                    id=str(uuid4()),
                    market_id=market.market_id,
                    question=market.question,
                    price=price,
                    remaining_seconds=remaining,
                    reason="CLOB强信号",
                    created_at=now,
                ),
            )
        await manager.broadcast("market_update", market)

    async def _handle_resolved(self, market_id: str) -> None:
        async with self._lock:
            market = self._markets.get(market_id)
            if market:
                market.status = "resolved"
        if market:
            await manager.broadcast("market_update", market)
            await manager.broadcast(
                "push_event",
                PushEvent(
                    id=str(uuid4()),
                    market_id=market.market_id,
                    question=market.question,
                    reason="市场结束",
                    created_at=datetime.now(UTC),
                ),
            )


def _extract_live_price(event: dict) -> float | None:
    for key in ("best_bid", "best_ask", "price", "bid", "last_price"):
        if event.get(key) is not None:
            try:
                return float(event[key])
            except (TypeError, ValueError):
                return None
    bids = event.get("bids")
    if isinstance(bids, list) and bids:
        try:
            return max(float(item["price"]) for item in bids if item.get("price") is not None)
        except (TypeError, ValueError):
            pass
    if event.get("changes") and isinstance(event["changes"], list):
        for change in event["changes"]:
            if change.get("price") is not None:
                try:
                    return float(change["price"])
                except (TypeError, ValueError):
                    continue
    return None


def _change_since(history: list[tuple[datetime, float]], now: datetime, seconds: int) -> float | None:
    if not history:
        return None
    current = history[-1][1]
    older = next((value for at, value in history if now - at <= timedelta(seconds=seconds)), None)
    if older is None:
        return None
    return current - older


def _should_push(market: MonitorMarket, now: datetime) -> bool:
    if (market.clob_probability or 0) < 0.90:
        return False
    if market.clob_spread is None or market.clob_spread > 0.03:
        return False
    if market.last_trade_at is None or now - market.last_trade_at > timedelta(minutes=5):
        return False
    if (market.liquidity or 0) < 1000:
        return False
    tags = set(market.status_tags or [])
    if "ClosedRisk" in tags or "StaleBook" in tags:
        return False
    return market.score >= 70


def _clob_priority_key(market: MonitorMarket) -> tuple[int, int, int, float]:
    probability = market.last_price or max(market.outcomePrices or [0])
    liquidity = market.liquidity or 0
    category_rank = 1 if market.category == "Weather" else 0
    kind_rank = {"sports": 0, "crypto": 1, "esports": 2, "general": 3}.get(market.kind, 4)
    useful_probability = 0 if 0.80 <= probability < 0.995 else 1
    liquidity_rank = 0 if liquidity >= 10_000 else 1 if liquidity >= 1_000 else 2
    return category_rank, kind_rank, useful_probability, liquidity_rank, -probability


clob_stream = ClobMarketStream()
