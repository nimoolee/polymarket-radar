from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from .clob_ws import clob_stream
from .config import settings
from .gamma import fetch_filtered_markets, fetch_hot_crypto_markets
from .hub import manager
from .models import MonitorMarket
from .orderbook import enrich_orderbooks

UTC = timezone.utc

class MarketStore:
    def __init__(self) -> None:
        self._markets: dict[str, MonitorMarket] = {}
        self._candidate_first_seen: dict[str, datetime] = {}
        self.last_scan_started_at: datetime | None = None
        self.last_scan_completed_at: datetime | None = None
        self.last_clob_scan_completed_at: datetime | None = None
        self.scanning_enabled = settings.scanning_enabled_default
        self._lock = asyncio.Lock()

    async def set_scanning_enabled(self, enabled: bool) -> None:
        async with self._lock:
            self.scanning_enabled = enabled
            snapshot = self._markets.copy() if enabled else {}
        await clob_stream.set_enabled(enabled)
        await clob_stream.sync_markets(snapshot)
        await manager.broadcast(
            "connection_status",
            {
                "scanner": "running" if enabled else "paused",
                "gamma": "unknown" if enabled else "paused",
                "crypto_hot": "unknown" if enabled else "paused",
                "clob_scan": "unknown" if enabled else "paused",
            },
        )

    async def list_markets(self) -> list[MonitorMarket]:
        async with self._lock:
            return sorted(
                (market for market in self._markets.values() if not _should_drop_market(market, datetime.now(UTC))),
                key=_market_sort_key,
            )

    async def refresh(self) -> None:
        self.last_scan_started_at = datetime.now(UTC)
        fetched = await fetch_filtered_markets()
        now = datetime.now(UTC)
        async with self._lock:
            fetched_ids = {market.market_id for market in fetched}
            for market_id in list(self._markets):
                first_seen = self._candidate_first_seen.get(market_id, now)
                if market_id not in fetched_ids and now - first_seen >= timedelta(minutes=30):
                    del self._markets[market_id]
                    self._candidate_first_seen.pop(market_id, None)
            for market in fetched:
                self._candidate_first_seen.setdefault(market.market_id, now)
                existing = self._markets.get(market.market_id)
                if existing:
                    _carry_live_fields(existing, market)
                self._markets[market.market_id] = market
            self._apply_market_state(now)
            snapshot = self._markets.copy()
            self.last_scan_completed_at = now
        await clob_stream.sync_markets(snapshot)
        await manager.broadcast("markets_snapshot", await self.list_markets())

    async def refresh_crypto_hot(self) -> None:
        fetched = await fetch_hot_crypto_markets()
        now = datetime.now(UTC)
        async with self._lock:
            for market in fetched:
                existing = self._markets.get(market.market_id)
                if existing:
                    _carry_live_fields(existing, market)
                self._markets[market.market_id] = market
                self._candidate_first_seen.setdefault(market.market_id, now)
            self._apply_market_state(now)
            snapshot = self._markets.copy()
        await clob_stream.sync_markets(snapshot)
        await manager.broadcast("markets_snapshot", await self.list_markets())

    async def refresh_clob_prices(self) -> None:
        now = datetime.now(UTC)
        async with self._lock:
            targets = _clob_scan_targets(list(self._markets.values()), now)
        await enrich_orderbooks(targets)
        now = datetime.now(UTC)
        async with self._lock:
            for market in targets:
                self._markets[market.market_id] = market
            self._apply_market_state(now)
            snapshot = self._markets.copy()
            self.last_clob_scan_completed_at = now
        await clob_stream.sync_markets(snapshot)
        await manager.broadcast("markets_snapshot", await self.list_markets())

    async def run_poll_loop(self) -> None:
        while True:
            try:
                if self.scanning_enabled:
                    await self.refresh()
                    await manager.broadcast("connection_status", {"gamma": "ok", "clob": "mock" if settings.use_mock_data else "connected", "scanner": "running"})
                else:
                    await manager.broadcast("connection_status", {"gamma": "paused", "scanner": "paused"})
            except Exception as exc:
                await manager.broadcast("connection_status", {"gamma": "error", "error": repr(exc)})
            await asyncio.sleep(settings.poll_interval_seconds)

    async def run_clob_scan_loop(self) -> None:
        while True:
            try:
                if self.scanning_enabled:
                    await self.refresh_clob_prices()
                else:
                    await manager.broadcast("connection_status", {"clob_scan": "paused"})
            except Exception as exc:
                await manager.broadcast("connection_status", {"clob_scan": "error", "error": str(exc)})
            await asyncio.sleep(settings.clob_scan_interval_seconds)

    async def run_crypto_hot_loop(self) -> None:
        while True:
            try:
                if self.scanning_enabled:
                    await self.refresh_crypto_hot()
                else:
                    await manager.broadcast("connection_status", {"crypto_hot": "paused"})
            except Exception as exc:
                await manager.broadcast("connection_status", {"crypto_hot": "error", "error": repr(exc)})
            await asyncio.sleep(settings.crypto_poll_interval_seconds)

    def _apply_market_state(self, now: datetime) -> None:
        for market_id, market in list(self._markets.items()):
            deadline = _scan_deadline(market)
            if market.closed or (market.kind == "crypto" and deadline and deadline <= now):
                market.status = "resolved"
            elif deadline and timedelta(seconds=0) <= deadline - now <= timedelta(hours=1):
                market.status = "ending"
            else:
                market.status = "active"
            market.status_tags = _status_tags(market, now, self._candidate_first_seen.get(market_id))
            market.score = _score_market(market, now)
            if _should_drop_market(market, now):
                del self._markets[market_id]


def _market_sort_key(market: MonitorMarket) -> tuple[int, int, int, int, int, int, float, float]:
    now = datetime.now(UTC)
    remaining = _remaining_seconds(market, now)
    probability = market.clob_probability or 0
    liquidity = market.liquidity or 0
    volume = market.volume or 0
    return (
        _display_bucket(market, now),
        _risk_rank(market),
        _urgency_bucket(market, remaining),
        remaining,
        -int(market.score),
        _liquidity_bucket(liquidity),
        -probability,
        -volume,
    )


def _remaining_seconds(market: MonitorMarket, now: datetime) -> int:
    target = _scan_deadline(market)
    if not target:
        return 10**12
    return max(0, int((target - now).total_seconds()))


def _should_drop_market(market: MonitorMarket, now: datetime) -> bool:
    deadline = _scan_deadline(market)
    if market.closed or market.status == "resolved":
        return True
    if deadline and deadline - now > timedelta(hours=settings.discovery_horizon_hours):
        return True
    if market.kind == "crypto" and deadline and deadline <= now:
        return True
    effective_clob = max(value for value in (market.clob_probability, market.last_trade_price, 0) if value is not None)
    if effective_clob >= 0.999:
        return True
    if market.kind in {"sports", "esports"} and market.game_start_time:
        if now - market.game_start_time <= timedelta(hours=_sports_live_window_hours(market)):
            return False
        if market.orderbook_updated_at and now - market.orderbook_updated_at <= timedelta(seconds=75):
            return False
        return True
    return False


def _sports_live_rank(market: MonitorMarket, now: datetime) -> int:
    if market.kind not in {"sports", "esports"} or not market.game_start_time:
        return 1
    tags = set(market.status_tags or [])
    if market.game_start_time <= now and "ClosedRisk" not in tags and "StaleBook" not in tags:
        return 0
    if market.game_start_time > now:
        return 2
    return 3


def _risk_rank(market: MonitorMarket) -> int:
    tags = set(market.status_tags or [])
    if "ClosedRisk" in tags:
        return 3
    if "StaleBook" in tags:
        return 2
    return 0


def _carry_live_fields(existing: MonitorMarket, market: MonitorMarket) -> None:
    for field in (
        "clob_probability",
        "gamma_clob_diff",
        "clob_best_bid",
        "clob_best_ask",
        "clob_spread",
        "clob_depth",
        "orderbook_updated_at",
        "tradable",
        "last_trade_price",
        "last_trade_at",
        "price_change_30s",
        "price_change_3m",
        "status_tags",
        "score",
    ):
        value = getattr(existing, field, None)
        if value is not None and value != []:
            setattr(market, field, value)
    market.last_price = existing.clob_probability or existing.last_price or market.last_price
    market.best_bid = existing.best_bid or market.best_bid
    market.best_ask = existing.best_ask or market.best_ask
    if existing.price_source.startswith("clob"):
        market.price_source = existing.price_source


def _clob_scan_targets(markets: list[MonitorMarket], now: datetime) -> list[MonitorMarket]:
    pooled = [
        market
        for market in markets
        if _in_candidate_pool(market, now) or _in_near_end_pool(market, now) or _in_live_sports_pool(market, now)
    ]
    return sorted(pooled, key=lambda market: _clob_target_key(market, now))[: settings.clob_orderbook_check_limit]


def _in_candidate_pool(market: MonitorMarket, now: datetime) -> bool:
    deadline = _scan_deadline(market)
    if not deadline or deadline - now > timedelta(hours=48):
        return False
    if market.closed or market.status == "resolved":
        return False
    if deadline <= now and not _is_recent_active_general(market, now):
        return False
    return (market.gamma_probability or max(market.outcomePrices or [0])) >= 0.80 and (market.liquidity or 0) >= 1000


def _in_near_end_pool(market: MonitorMarket, now: datetime) -> bool:
    deadline = _scan_deadline(market)
    if not deadline or (market.liquidity or 0) < 1000:
        return False
    if timedelta(seconds=0) < deadline - now <= timedelta(hours=6):
        return True
    return _is_recent_active_general(market, now)


def _is_recent_active_general(market: MonitorMarket, now: datetime) -> bool:
    deadline = _scan_deadline(market)
    category = (market.category or "").lower()
    text = f"{market.question} {' '.join(market.tags or [])} {market.category}".lower()
    settlement_like = any(
        term in text
        for term in (
            "box office",
            "opening weekend",
            "rotten tomatoes",
            "tomatometer",
            "views",
            "tweets",
            "mentions",
            "youtube",
            "spotify",
            "instagram",
            "culture",
            "movies",
            "pop-culture",
        )
    )
    return bool(
        market.kind == "general"
        and category not in {"crypto", "finance", "weather"}
        and settlement_like
        and deadline
        and market.active
        and not market.closed
        and timedelta(hours=-24) <= deadline - now <= timedelta(seconds=0)
    )


def _in_live_sports_pool(market: MonitorMarket, now: datetime) -> bool:
    if market.kind not in {"sports", "esports"} or not market.game_start_time:
        return False
    if market.closed or market.status == "resolved":
        return False
    if now < market.game_start_time:
        return False
    if now - market.game_start_time > timedelta(hours=_sports_live_window_hours(market)):
        return False
    probability = market.gamma_probability or max(market.outcomePrices or [0])
    return probability >= 0.80 and (market.liquidity or 0) >= 1000


def _scan_deadline(market: MonitorMarket) -> datetime | None:
    if market.kind in {"sports", "esports"} and market.game_start_time:
        return market.game_start_time
    if market.time_basis in {
        "by_date_et_rules",
        "inclusive_period_et_rules",
        "explicit_datetime_et_rules",
        "event_date_et_rules",
        "election_date_et_rules",
    }:
        return market.real_deadline or market.endDate
    if market.kind == "general" and market.category != "Weather":
        return market.endDate or market.real_deadline
    return market.real_deadline or market.endDate


def _clob_target_key(market: MonitorMarket, now: datetime) -> tuple[int, int, int, int, int, float]:
    remaining = _remaining_seconds(market, now)
    liquidity = market.liquidity or 0
    probability = market.gamma_probability or max(market.outcomePrices or [0])
    liquidity_rank = 0 if liquidity >= 10_000 else 1 if liquidity >= 1_000 else 2
    return (
        _scan_bucket(market, now),
        _scan_staleness_bucket(market, now),
        _probability_bucket(probability),
        liquidity_rank,
        remaining,
        -probability,
    )


def _display_bucket(market: MonitorMarket, now: datetime) -> int:
    tags = set(market.status_tags or [])
    if market.kind in {"sports", "esports"}:
        if not market.game_start_time:
            return 8
        if now < market.game_start_time:
            return 6
        if "ClosedRisk" in tags:
            return 7
        if "StaleBook" in tags:
            return 5
        if market.clob_spread is None or market.score <= 0:
            return 4
        return 0
    if market.clob_probability is None:
        return 4
    if "StaleBook" in tags:
        return 5
    if "ClosedRisk" in tags:
        return 7
    if market.kind == "crypto":
        return 1
    return 2


def _scan_bucket(market: MonitorMarket, now: datetime) -> int:
    deadline = _scan_deadline(market)
    remaining = (deadline - now).total_seconds() if deadline else 10**12
    if market.kind == "crypto" and 0 <= remaining <= 30 * 60:
        return 0
    if market.kind in {"sports", "esports"} and market.game_start_time:
        if market.game_start_time <= now <= market.game_start_time + timedelta(hours=_sports_live_window_hours(market)):
            return 1
        if 0 < (market.game_start_time - now).total_seconds() <= 30 * 60:
            return 2
    if deadline and 0 <= remaining <= 6 * 3600:
        return 3
    return 4


def _scan_staleness_bucket(market: MonitorMarket, now: datetime) -> int:
    if not market.orderbook_updated_at:
        return 0
    age = (now - market.orderbook_updated_at).total_seconds()
    if age > 45:
        return 0
    if age > 20:
        return 1
    return 2


def _probability_bucket(probability: float) -> int:
    if 0.80 <= probability < 0.995:
        return 0
    if 0.995 <= probability < 0.999:
        return 1
    return 2


def _status_tags(market: MonitorMarket, now: datetime, first_seen: datetime | None) -> list[str]:
    tags = ["Candidate"]
    deadline = _scan_deadline(market)
    if market.clob_probability is not None:
        tags.append("LivePriceOK")
    if market.gamma_clob_diff is not None and abs(market.gamma_clob_diff) >= 0.05:
        tags.append("GammaLag")
    if abs(market.price_change_30s or 0) >= settings.price_move_threshold:
        tags.append("HotMove")
    if deadline and timedelta(seconds=0) < deadline - now <= timedelta(hours=6):
        tags.append("NearEnd")
    if not market.orderbook_updated_at or now - market.orderbook_updated_at > timedelta(seconds=75):
        tags.append("StaleBook")
    if market.closed or market.status == "resolved" or _has_closed_risk(market, now):
        tags.append("ClosedRisk")
    if market.tradable:
        tags.append("Tradable")
    if market.tradable is False or "ClosedRisk" in tags:
        tags.append("Ignore")
    return tags


def _has_closed_risk(market: MonitorMarket, now: datetime) -> bool:
    deadline = _scan_deadline(market)
    if market.kind in {"sports", "esports"} and market.game_start_time:
        return now - market.game_start_time > timedelta(hours=_sports_live_window_hours(market))
    return bool(deadline and deadline <= now)


def _score_market(market: MonitorMarket, now: datetime) -> float:
    probability = market.clob_probability
    if probability is None:
        return 0
    deadline = _scan_deadline(market)
    hours = max(0, (deadline - now).total_seconds() / 3600) if deadline else 999
    liquidity = market.liquidity or 0
    spread = market.clob_spread
    if liquidity < 1000 or probability < 0.80 or spread is None:
        return 0
    if "ClosedRisk" in market.status_tags or "StaleBook" in market.status_tags:
        return 0
    prob_score = min(34, max(0, (probability - 0.80) * 170))
    time_score = max(0, 26 - hours * 2.2)
    liquidity_score = min(20, max(0, __import__("math").log10(max(1, liquidity / 1000)) * 10))
    spread_score = max(0, 16 - spread * 400)
    momentum_score = min(8, abs(market.price_change_30s or 0) * 300 + abs(market.price_change_3m or 0) * 120)
    return round(prob_score + time_score + liquidity_score + spread_score + momentum_score, 1)


def _sports_live_window_hours(market: MonitorMarket) -> float:
    return 3.5


def _urgency_bucket(market: MonitorMarket, remaining: int) -> int:
    if market.status == "resolved":
        return 9
    if market.status == "ending" or remaining <= 3600:
        return 0
    if remaining <= 6 * 3600:
        return 1
    if remaining <= 24 * 3600:
        return 2
    if remaining <= 7 * 24 * 3600:
        return 3
    return 4


def _liquidity_bucket(liquidity: float) -> int:
    if liquidity >= 10_000:
        return 0
    if liquidity >= 1_000:
        return 1
    if liquidity >= 250:
        return 2
    return 3


market_store = MarketStore()
