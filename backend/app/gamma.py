from __future__ import annotations

import json
import re
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import settings
from .mock_data import mock_gamma_markets
from .models import MonitorMarket

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
WEATHER_CITY_TIMEZONES = {
    "amsterdam": "Europe/Amsterdam",
    "ankara": "Europe/Istanbul",
    "atlanta": "America/New_York",
    "austin": "America/Chicago",
    "beijing": "Asia/Shanghai",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "busan": "Asia/Seoul",
    "cape town": "Africa/Johannesburg",
    "chengdu": "Asia/Shanghai",
    "chicago": "America/Chicago",
    "chongqing": "Asia/Shanghai",
    "dallas": "America/Chicago",
    "denver": "America/Denver",
    "guangzhou": "Asia/Shanghai",
    "helsinki": "Europe/Helsinki",
    "hong kong": "Asia/Hong_Kong",
    "houston": "America/Chicago",
    "istanbul": "Europe/Istanbul",
    "jakarta": "Asia/Jakarta",
    "jeddah": "Asia/Riyadh",
    "karachi": "Asia/Karachi",
    "kuala lumpur": "Asia/Kuala_Lumpur",
    "lagos": "Africa/Lagos",
    "london": "Europe/London",
    "los angeles": "America/Los_Angeles",
    "lucknow": "Asia/Kolkata",
    "madrid": "Europe/Madrid",
    "manila": "Asia/Manila",
    "mexico city": "America/Mexico_City",
    "miami": "America/New_York",
    "milan": "Europe/Rome",
    "moscow": "Europe/Moscow",
    "munich": "Europe/Berlin",
    "new york": "America/New_York",
    "new york city": "America/New_York",
    "panama city": "America/Panama",
    "paris": "Europe/Paris",
    "qingdao": "Asia/Shanghai",
    "sao paulo": "America/Sao_Paulo",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "seoul": "Asia/Seoul",
    "shanghai": "Asia/Shanghai",
    "shenzhen": "Asia/Shanghai",
    "singapore": "Asia/Singapore",
    "taipei": "Asia/Taipei",
    "tel aviv": "Asia/Jerusalem",
    "tokyo": "Asia/Tokyo",
    "toronto": "America/Toronto",
    "warsaw": "Europe/Warsaw",
    "wellington": "Pacific/Auckland",
    "wuhan": "Asia/Shanghai",
}
SPORT_TAGS = {
    "nba",
    "nfl",
    "nhl",
    "mlb",
    "soccer",
    "epl",
    "ufc",
    "tennis",
    "sports",
    "football",
    "basketball",
    "baseball",
    "hockey",
}
ESPORT_TAGS = {
    "esports",
    "counter-strike",
    "cs2",
    "dota",
    "valorant",
    "league of legends",
}
SPORT_INCLUDE = ("win", "winner", "moneyline")
CRYPTO_TAGS = {
    "btc",
    "bitcoin",
    "eth",
    "ethereum",
    "sol",
    "solana",
    "xrp",
    "doge",
    "dogecoin",
    "bnb",
    "hype",
    "hyperliquid",
}
CRYPTO_15M_TICKERS = ("btc", "eth", "sol", "xrp")
FINANCE_DAILY_TICKERS = ("aapl", "msft", "nvda", "tsla", "googl", "meta", "amzn", "spy")
SPORT_SUPPLEMENT_TAG_IDS = (
    "864",  # tennis
    "102650",  # Saudi Professional League
    "745",  # NBA
    "899",  # NHL
    "100381",  # MLB
    "100254",  # WNBA
)
WEATHER_SUPPLEMENT_TAG_ID = "84"
SOCCER_SUPPLEMENT_TAG_ID = "100350"
SOCCER_SUPPLEMENT_OFFSETS = tuple(range(0, 1000, 100))
GENERAL_CLOSE_HOURS = 24
GENERAL_SETTLEMENT_GRACE_HOURS = 24
SPORTS_LIVE_WINDOW_HOURS = 3.5
SPORTS_LOOKAHEAD_HOURS = 0.25
MAX_USEFUL_PROBABILITY = 0.999


def _parse_jsonish(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [value]
    return value


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        if normalized.endswith("+00"):
            normalized = f"{normalized}:00"
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _extract_tags(raw: dict) -> list[str]:
    tags: list[str] = []
    for key in ("tags", "series"):
        for item in _parse_jsonish(raw.get(key)):
            if isinstance(item, dict):
                tags.extend(str(item.get(k, "")) for k in ("label", "slug", "title", "ticker") if item.get(k))
            elif item:
                tags.append(str(item))
    for key in ("sports_market_type", "sportsMarketType"):
        if raw.get(key):
            tags.append(str(raw[key]))
    return sorted({tag.strip() for tag in tags if tag and tag.strip()})


def _extract_token_ids(raw: dict) -> list[str]:
    for key in ("clobTokenIds", "clob_token_ids", "clobTokenIDs"):
        tokens = _parse_jsonish(raw.get(key))
        if isinstance(tokens, list):
            return [str(token) for token in tokens if token]
    return []


def _extract_prices(raw: dict) -> list[float]:
    prices = _parse_jsonish(raw.get("outcomePrices"))
    parsed: list[float] = []
    for price in prices if isinstance(prices, list) else []:
        try:
            parsed.append(float(price))
        except (TypeError, ValueError):
            continue
    return parsed


def _extract_outcomes(raw: dict) -> list[str]:
    outcomes = _parse_jsonish(raw.get("outcomes"))
    if not isinstance(outcomes, list):
        return []
    return [str(outcome) for outcome in outcomes]


def _extract_market_url(raw: dict) -> str | None:
    for key in ("url", "marketUrl", "market_url"):
        value = raw.get(key)
        if value:
            return str(value) if str(value).startswith("http") else f"https://polymarket.com{value}"

    events = _parse_jsonish(raw.get("events"))
    if isinstance(events, list) and events:
        event = events[0]
        if isinstance(event, dict) and event.get("slug"):
            return f"https://polymarket.com/event/{event['slug']}"

    for key in ("eventSlug", "event_slug", "groupSlug"):
        value = raw.get(key)
        if value:
            return f"https://polymarket.com/event/{value}"
    if raw.get("slug") and raw.get("events"):
        return f"https://polymarket.com/event/{raw['slug']}"
    return None


def _extract_float(raw: dict, *keys: str) -> float | None:
    for key in keys:
        value = raw.get(key)
        if value is not None and value != "":
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _extract_category(tags: list[str], raw: dict) -> str:
    for tag in tags:
        lowered = tag.lower()
        if lowered in {"crypto", "sports", "politics", "finance", "weather", "economy", "tech", "culture", "elections"}:
            return tag
    title_blob = f"{raw.get('question', '')} {raw.get('title', '')}".lower()
    blob = f"{title_blob} {raw.get('description', '')}".lower()
    if any(term in blob for term in ("election", "primary", "senate", "president", "trump", "biden")):
        return "Politics"
    if any(term in blob for term in ("stock", "nasdaq", "s&p", "dow jones", "aapl", "nvda", "tesla")):
        return "Finance"
    if any(term in blob for term in ("iran", "ceasefire", "diplomacy", "airspace", "geopolitics")):
        return "Politics"
    if _looks_like_weather_text(title_blob):
        return "Weather"
    return str(raw.get("category") or raw.get("seriesTicker") or "General")


def _looks_like_weather_text(blob: str) -> bool:
    return bool(
        re.search(
            r"\b(temperature|weather|rain|snow|hurricane|wunderground|wind\s+speed|precipitation|forecast)\b",
            blob,
        )
    )


def _is_closed(raw: dict) -> bool:
    return bool(raw.get("closed") or raw.get("resolved") or raw.get("archived"))


def _is_active(raw: dict) -> bool:
    if raw.get("active") is False:
        return False
    return not _is_closed(raw)


def _is_sports_market(raw: dict, tags: list[str], now: datetime) -> bool:
    game_start = _extract_game_start(raw)
    if not game_start:
        return False
    live_window = _sports_live_window_hours(raw, tags)
    return (
        _looks_like_sports_or_esports(raw, tags)
        and _is_sports_moneyline_candidate(raw, tags)
        and not _is_sports_derivative(raw, tags)
        and _has_candidate_probability(_extract_prices(raw))
        and now - timedelta(hours=live_window) <= game_start <= now + timedelta(hours=SPORTS_LOOKAHEAD_HOURS)
    )


def _sports_live_window_hours(raw: dict, tags: list[str]) -> float:
    return SPORTS_LIVE_WINDOW_HOURS


def _extract_game_start(raw: dict) -> datetime | None:
    for value in (raw.get("game_start_time"), raw.get("gameStartTime"), raw.get("startTime")):
        if parsed := _parse_dt(value):
            return parsed
    events = _parse_jsonish(raw.get("events"))
    if isinstance(events, list) and events:
        event = events[0]
        if isinstance(event, dict):
            return _parse_dt(event.get("startTime") or event.get("startDate") or event.get("startDateIso"))
    return None


def _looks_like_sports_or_esports(raw: dict, tags: list[str]) -> bool:
    return _looks_like_sports(raw, tags) or _looks_like_esports(raw, tags)


def _looks_like_sports(raw: dict, tags: list[str]) -> bool:
    blob = _market_blob(raw, tags)
    return (
        any(_contains_market_term(blob, tag) for tag in SPORT_TAGS)
        or bool(_extract_game_start(raw) and _sports_market_type(raw) in {"moneyline", "win", "winner"})
    )


def _looks_like_esports(raw: dict, tags: list[str]) -> bool:
    blob = _market_blob(raw, tags)
    return any(_contains_market_term(blob, tag) for tag in ESPORT_TAGS) or "(bo" in blob


def _contains_market_term(blob: str, term: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", blob))


def _market_blob(raw: dict, tags: list[str]) -> str:
    return f"{raw.get('question', '')} {' '.join(tags)} {raw.get('category', '')} {raw.get('seriesTicker', '')} {raw.get('description', '')}".lower()


def _sports_market_type(raw: dict) -> str:
    return str(raw.get("sports_market_type") or raw.get("sportsMarketType") or "").lower()


def _is_sports_moneyline_candidate(raw: dict, tags: list[str]) -> bool:
    question = str(raw.get("question", "")).lower()
    tag_blob = " ".join(tags).lower()
    outcomes = _extract_outcomes(raw)
    has_matchup = " vs " in question or " v " in question
    binary_sides = len(outcomes) == 2 and not {"over", "under", "yes", "no"}.intersection({outcome.lower() for outcome in outcomes})
    yes_no_draw = len(outcomes) == 2 and {"yes", "no"} == {outcome.lower() for outcome in outcomes} and "draw" in question
    return (
        any(term in question or term in tag_blob for term in SPORT_INCLUDE)
        or _sports_market_type(raw) in {"moneyline", "win", "winner"}
        or (has_matchup and binary_sides)
        or ("tennis" in tag_blob and binary_sides)
        or yes_no_draw
    )


def _is_sports_derivative(raw: dict, tags: list[str]) -> bool:
    blob = f"{raw.get('question', '')} {' '.join(tags)} {raw.get('groupItemTitle', '')}".lower()
    return _contains_derivative_term(blob)


def _is_derivative_bet_question(raw: dict) -> bool:
    blob = f"{raw.get('question', '')} {raw.get('groupItemTitle', '')}".lower()
    return _contains_derivative_term(blob)


def _contains_derivative_term(blob: str) -> bool:
    patterns = (
        r"\bmap\s+\d*\b",
        r"\bset\s+\d+\b",
        r"\bset\s+\d+\s+winner\b",
        r"\bset\s+winner\b",
        r"\bperiod\s+\d+\b",
        r"\bquarter\s+\d+\b",
        r"\b[1234](?:st|nd|rd|th)\s+quarter\b",
        r"\bhalf\b",
        r"\b1st\s+half\b",
        r"\b2nd\s+half\b",
        r"\bgame\s+handicap\b",
        r"\bmap\s+handicap\b",
        r"\bhandicap\b",
        r"\bspread\b",
        r"\btotal(?:s)?\b",
        r"\bo/u\b",
        r"\bover\s*/\s*under\b",
        r"\bover\s+\d",
        r"\bunder\s+\d",
        r"\bodd/even\b",
        r"\brounds\b",
        r"\bkills\b",
        r"\bcorrect score\b",
        r"\bpoints\b",
        r"\brebounds\b",
        r"\bassists\b",
        r"\btouchdowns\b",
        r"\byards\b",
        r"\bplayer\b",
        r"\bprop\b",
        r"\bgame\s+\d+:",
        r"\broshan\b",
        r"\bexact score\b",
        r"\bgoalscorer\b",
        r"\banytime\s+goalscorer\b",
        r"\bleading\s+at\s+halftime\b",
        r"\bat\s+halftime\b",
        r"\b1h\b",
        r"\bpromotion\b",
        r"\bpromoted\b",
        r"\brelegation\b",
        r"\bseason\b",
        r"\bchampion(?:ship)?\b",
        r"\bleague\s+winner\b",
        r"\btop\s+scorer\b",
    )
    return any(re.search(pattern, blob) for pattern in patterns)


def _has_useful_probability(prices: list[float]) -> bool:
    return any(settings.high_probability_threshold <= price < MAX_USEFUL_PROBABILITY for price in prices)


def _has_candidate_probability(prices: list[float]) -> bool:
    return any(settings.high_probability_threshold <= price <= 1 for price in prices)


def _has_observable_probability(prices: list[float]) -> bool:
    return any(0.01 <= price < MAX_USEFUL_PROBABILITY for price in prices)


def _is_crypto_market(raw: dict, tags: list[str], prices: list[float], now: datetime) -> bool:
    end_date = _parse_dt(raw.get("endDate") or raw.get("end_date"))
    if not end_date:
        return False
    blob = f"{raw.get('question', '')} {' '.join(tags)}".lower()
    remaining = end_date - now
    window_minutes = _crypto_window_minutes(raw)
    return (
        any(_contains_market_term(blob, tag) for tag in CRYPTO_TAGS)
        and remaining >= timedelta(seconds=0)
        and window_minutes > 5
        and (
            _has_useful_probability(prices)
            or (
                10 <= window_minutes <= 30
                and remaining <= timedelta(hours=2)
                and _has_observable_probability(prices)
                and (_extract_float(raw, "liquidityNum", "liquidity", "liquidityClob") or 0) >= 1000
            )
        )
    )


def _crypto_window_minutes(raw: dict) -> float:
    text = str(raw.get("question") or raw.get("title") or "")
    match = re.search(
        r"(\d{1,2}):(\d{2})\s*(AM|PM)?\s*-\s*(\d{1,2}):(\d{2})\s*(AM|PM)?",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return float("inf")
    start_hour, start_minute, start_period, end_hour, end_minute, end_period = match.groups()
    end_period = (end_period or start_period or "").upper()
    start_period = (start_period or end_period or "").upper()
    start = _clock_minutes(int(start_hour), int(start_minute), start_period)
    end = _clock_minutes(int(end_hour), int(end_minute), end_period)
    if end <= start:
        end += 24 * 60
    return end - start


def _clock_minutes(hour: int, minute: int, period: str) -> int:
    if period == "AM" and hour == 12:
        hour = 0
    elif period == "PM" and hour != 12:
        hour += 12
    return hour * 60 + minute


def _is_general_candidate(raw: dict, prices: list[float], now: datetime) -> bool:
    end_date = _parse_dt(raw.get("endDate") or raw.get("end_date"))
    if not end_date:
        return False
    rules = _extract_rules(raw)
    deadline = (
        _parse_by_month_day_et(raw, rules)
        or _parse_inclusive_period_et(raw, rules)
        or _parse_election_date_et(raw, rules)
        or _parse_explicit_datetime_et(raw, rules)
        or _parse_event_date_et(raw, rules)
        or end_date
    )
    remaining = deadline - now
    tags = _extract_tags(raw)
    if _looks_like_sports_or_esports(raw, tags) or _looks_like_crypto_price_market(raw, tags) or _is_derivative_bet_question(raw):
        return False
    grace_allowed = _allows_general_settlement_grace(raw)
    return (
        _is_active(raw)
        and (remaining >= timedelta(seconds=0) or (grace_allowed and remaining >= -timedelta(hours=GENERAL_SETTLEMENT_GRACE_HOURS)))
        and _has_useful_probability(prices)
    )


def _looks_like_crypto_price_market(raw: dict, tags: list[str]) -> bool:
    blob = _market_blob(raw, tags)
    category = str(raw.get("category") or raw.get("seriesTicker") or "").lower()
    has_crypto_context = category == "crypto" or any(_contains_market_term(blob, tag) for tag in CRYPTO_TAGS)
    if not has_crypto_context:
        return False
    return (
        "up or down" in blob
        or _crypto_window_minutes(raw) != float("inf")
        or bool(re.search(r"\b(?:above|below)\s+[\d,$.]+", blob))
    )


def _allows_general_settlement_grace(raw: dict) -> bool:
    tags = _extract_tags(raw)
    category = _extract_category(tags, raw).lower()
    blob = _market_blob(raw, tags)
    if category in {"crypto", "finance", "weather", "sports"}:
        return False
    if any(_contains_market_term(blob, term) for term in CRYPTO_TAGS):
        return False
    if any(term in blob for term in ("stock", "nasdaq", "s&p", "dow jones", "aapl", "msft", "nvda", "tesla", "googl")):
        return False
    return any(
        term in blob
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


def normalize_market(raw: dict, now: datetime | None = None) -> MonitorMarket | None:
    now = now or datetime.now(UTC)
    tags = _extract_tags(raw)
    prices = _extract_prices(raw)
    if _is_derivative_bet_question(raw) or (_looks_like_sports_or_esports(raw, tags) and _is_sports_derivative(raw, tags)):
        return None
    is_sports = _is_sports_market(raw, tags, now)
    is_crypto = _is_crypto_market(raw, tags, prices, now)
    is_general = _is_general_candidate(raw, prices, now)
    if not is_sports and not is_crypto and not is_general:
        return None

    end_date = _parse_dt(raw.get("endDate") or raw.get("end_date"))
    game_start = _extract_game_start(raw) if is_sports else None
    kind = "esports" if is_sports and _looks_like_esports(raw, tags) else "sports" if is_sports else "crypto" if is_crypto else "general"
    category = _extract_category(tags, raw)
    rules = _extract_rules(raw)
    real_deadline, time_basis = _interpret_deadline(raw, category, kind, end_date, game_start, rules)
    status = "resolved" if _is_closed(raw) else "active"
    near_deadline = bool(real_deadline and timedelta(seconds=0) <= real_deadline - now <= timedelta(hours=GENERAL_CLOSE_HOURS))
    if status == "active" and near_deadline:
        status = "ending"
    leading_index = max(range(len(prices)), key=prices.__getitem__) if prices else None
    outcomes = _extract_outcomes(raw)
    gamma_probability = prices[leading_index] if leading_index is not None else None
    last_trade_price = _extract_float(raw, "lastTradePrice", "last_trade_price")

    return MonitorMarket(
        market_id=str(raw.get("id") or raw.get("conditionId") or raw.get("market_id")),
        clob_token_ids=_extract_token_ids(raw),
        endDate=end_date,
        real_deadline=real_deadline,
        time_basis=time_basis,
        rules=rules,
        active=_is_active(raw),
        closed=_is_closed(raw),
        question=str(raw.get("question", "")),
        outcomePrices=prices,
        gamma_probability=gamma_probability,
        outcomes=outcomes,
        leading_outcome=outcomes[leading_index] if leading_index is not None and leading_index < len(outcomes) else None,
        game_start_time=game_start,
        tags=tags,
        market_url=_extract_market_url(raw),
        image=raw.get("icon") or raw.get("image"),
        volume=_extract_float(raw, "volumeNum", "volume", "volumeClob"),
        liquidity=_extract_float(raw, "liquidityNum", "liquidity", "liquidityClob"),
        category=category,
        kind=kind,
        best_bid=max(prices) if prices else None,
        best_ask=min(max(prices) + 0.005, 0.999) if prices else None,
        last_price=gamma_probability,
        last_trade_price=last_trade_price,
        status=status,
        updated_at=now,
    )


def _extract_rules(raw: dict) -> str | None:
    for key in ("rules", "description", "resolutionSource", "title"):
        value = raw.get(key)
        if value:
            return str(value)
    events = _parse_jsonish(raw.get("events"))
    if isinstance(events, list) and events:
        event = events[0]
        if isinstance(event, dict):
            for key in ("rules", "description", "title"):
                if event.get(key):
                    return str(event[key])
    return None


def _interpret_deadline(
    raw: dict,
    category: str,
    kind: str,
    end_date: datetime | None,
    game_start: datetime | None,
    rules: str | None,
) -> tuple[datetime | None, str]:
    if kind in {"sports", "esports"} and game_start:
        return game_start, "sports_start_time"
    if kind == "crypto":
        return end_date, "crypto_endDate"
    if explicit_datetime := _parse_explicit_datetime_et(raw, rules):
        return explicit_datetime, "explicit_datetime_et_rules"
    if inclusive_period := _parse_inclusive_period_et(raw, rules):
        return inclusive_period, "inclusive_period_et_rules"
    if by_may := _parse_by_month_day_et(raw, rules):
        return by_may, "by_date_et_rules"
    if election_date := _parse_election_date_et(raw, rules):
        return election_date, "election_date_et_rules"
    if event_date := _parse_event_date_et(raw, rules):
        return event_date, "event_date_et_rules"
    if category == "Weather":
        if weather_deadline := _parse_weather_local_day(raw):
            return weather_deadline, "weather_local_day"
        return end_date, "weather_close_time"
    return end_date, "endDate"


def _parse_by_month_day_et(raw: dict, rules: str | None) -> datetime | None:
    text = f"{raw.get('question', '')} {raw.get('title', '')} {rules or ''}"
    match = re.search(
        r"\bby\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(\d{4}))?",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    month_names = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month = month_names[match.group(1).lower()[:3]]
    day = int(match.group(2))
    year = int(match.group(3) or (raw.get("endDate", "")[:4] if raw.get("endDate") else datetime.now(ET).year))
    local_deadline = _safe_datetime(year, month, day, 23, 59, 59, ET)
    if not local_deadline:
        return None
    return local_deadline.astimezone(UTC)


def _parse_explicit_datetime_et(raw: dict, rules: str | None) -> datetime | None:
    text = f"{raw.get('question', '')} {raw.get('title', '')} {rules or ''}"
    matches = list(
        re.finditer(
            r"\b(?:by|until|after|on)\s+"
            r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\s+(\d{1,2}),?\s*(\d{4})?,?\s+"
            r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*ET\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    if not matches:
        return None
    match = matches[-1]
    month = _month_number(match.group(1))
    day = int(match.group(2))
    year = int(match.group(3) or (raw.get("endDate", "")[:4] if raw.get("endDate") else datetime.now(ET).year))
    hour = int(match.group(4))
    minute = int(match.group(5) or 0)
    if match.group(6).upper() == "AM" and hour == 12:
        hour = 0
    elif match.group(6).upper() == "PM" and hour != 12:
        hour += 12
    local_deadline = _safe_datetime(year, month, day, hour, minute, 59, ET)
    return local_deadline.astimezone(UTC) if local_deadline else None


def _parse_event_date_et(raw: dict, rules: str | None) -> datetime | None:
    text = f"{raw.get('question', '')} {raw.get('title', '')} {rules or ''}"
    if not re.search(r"\b(decision|announcement|meeting|release|report)\b", text, flags=re.IGNORECASE):
        return None
    matches = list(
        re.finditer(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\s+(\d{1,2}),?\s*(\d{4})\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    if not matches:
        return None
    end_date = _parse_dt(raw.get("endDate") or raw.get("end_date"))
    candidates = []
    for match in matches:
        local_deadline = _safe_datetime(
            int(match.group(3)),
            _month_number(match.group(1)),
            int(match.group(2)),
            23,
            59,
            59,
            ET,
        )
        if local_deadline:
            utc_deadline = local_deadline.astimezone(UTC)
            if not end_date or utc_deadline >= end_date:
                candidates.append(utc_deadline)
    return min(candidates) if candidates else None


def _parse_election_date_et(raw: dict, rules: str | None) -> datetime | None:
    end_date = _parse_dt(raw.get("endDate") or raw.get("end_date"))
    if not end_date:
        return None
    if (end_date.hour, end_date.minute, end_date.second) != (0, 0, 0):
        return None
    tags = _extract_tags(raw)
    text = f"{raw.get('question', '')} {raw.get('title', '')} {' '.join(tags)} {rules or ''}"
    if not re.search(
        r"\b(election|primary|runoff|nominee|nomination|senate|governor|mayor|ballot|vote|party)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return None
    local_deadline = _safe_datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, ET)
    if not local_deadline:
        return None
    return local_deadline.astimezone(UTC)


def _parse_inclusive_period_et(raw: dict, rules: str | None) -> datetime | None:
    text = f"{raw.get('question', '')} {raw.get('title', '')} {rules or ''}"
    patterns = (
        r"\bthrough\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(\d{4}))?\s*,?\s+inclusive\b",
        r"\bbetween\s+[a-z]+\s+\d{1,2}\s*[-–]\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)?\s*(\d{1,2})(?:,\s*(\d{4}))?",
        r"\b(?:from|for)\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\s*[-–]\s*(?:(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+)?(\d{1,2})(?:,\s*(\d{4}))?",
        r"\bbetween\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s*(?:\d{4})?,?\s+and\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(\d{4}))?",
        r"\b\d{1,2}/\d{1,2}\s*[-–]\s*(\d{1,2})/(\d{1,2})\b",
        r"\band\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(\d{4}))?,?\s+11:59\s*PM\s*ET\b",
        r"\bweek\s+of\s+[a-z]+\s+\d{1,2}.*?\bthrough\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(\d{4}))?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        month_text = match.group(1)
        if "/" in match.group(0) and len(match.groups()) == 2:
            month_text = match.group(1)
            day = int(match.group(2))
            year_text = raw.get("endDate", "")[:4] if raw.get("endDate") else None
        elif len(match.groups()) >= 4 and match.group(3) and re.fullmatch(r"\d{1,2}", match.group(3)):
            month_text = match.group(2) or month_text
            day = int(match.group(3))
            year_text = match.group(4)
        else:
            day = int(match.group(2))
            year_text = match.group(3)
        if not month_text:
            start_month = re.search(
                r"\bbetween\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}",
                text,
                flags=re.IGNORECASE,
            )
            if not start_month:
                continue
            month_text = start_month.group(1)
        month = int(month_text) if str(month_text).isdigit() else _month_number(month_text)
        year = int(year_text or (raw.get("endDate", "")[:4] if raw.get("endDate") else datetime.now(ET).year))
        local_deadline = _safe_datetime(year, month, day, 23, 59, 59, ET)
        if not local_deadline:
            return None
        return local_deadline.astimezone(UTC)
    return None


def _month_number(month_name: str) -> int:
    month_names = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    return month_names[month_name.lower()[:3]]


def _parse_weather_local_day(raw: dict) -> datetime | None:
    question = str(raw.get("question") or raw.get("title") or "")
    city_match = re.search(r"\b(?:in|at)\s+(.+?)\s+be\b", question, flags=re.IGNORECASE)
    date_match = re.search(
        r"\bon\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(\d{4}))?",
        question,
        flags=re.IGNORECASE,
    )
    if not city_match or not date_match:
        return None
    city = _normalize_weather_city(city_match.group(1))
    timezone_name = WEATHER_CITY_TIMEZONES.get(city)
    if not timezone_name:
        return None
    month_names = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month = month_names[date_match.group(1).lower()[:3]]
    day = int(date_match.group(2))
    year = int(date_match.group(3) or (str(raw.get("endDate") or "")[:4] if raw.get("endDate") else datetime.now(UTC).year))
    local_deadline = _safe_datetime(year, month, day, 23, 59, 59, ZoneInfo(timezone_name))
    if not local_deadline:
        return None
    return local_deadline.astimezone(UTC)


def _normalize_weather_city(city: str) -> str:
    return re.sub(r"\s+", " ", city.strip().lower().replace("ã", "a")).replace("são", "sao")


def _safe_datetime(year: int, month: int, day: int, hour: int, minute: int, second: int, tzinfo: ZoneInfo) -> datetime | None:
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=tzinfo)
    except ValueError:
        return None


def _window_params(now: datetime) -> dict[str, str]:
    window_end = now + timedelta(hours=settings.discovery_horizon_hours)
    window_start = now - timedelta(hours=GENERAL_SETTLEMENT_GRACE_HOURS)
    return {
        "end_date_min": window_start.isoformat().replace("+00:00", "Z"),
        "end_date_max": window_end.isoformat().replace("+00:00", "Z"),
    }


async def fetch_gamma_keyset_page(
    client: httpx.AsyncClient,
    endpoint: str,
    cursor: str | None,
    now: datetime,
    limit: int = 100,
) -> tuple[list[dict], str | None]:
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        **_window_params(now),
    }
    if cursor:
        params["cursor"] = cursor
    response = await client.get(
        f"{settings.gamma_api_url.rstrip('/')}/{endpoint}/keyset",
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return [], None
    rows = data.get(endpoint) or data.get("data") or []
    return rows if isinstance(rows, list) else [], data.get("next_cursor")


def _event_markets(event: dict) -> list[dict]:
    markets = _parse_jsonish(event.get("markets"))
    if not isinstance(markets, list):
        return []
    event_stub = {
        "id": event.get("id"),
        "slug": event.get("slug"),
        "title": event.get("title"),
        "startTime": event.get("startTime"),
        "startDate": event.get("startDate"),
        "endDate": event.get("endDate"),
    }
    enriched: list[dict] = []
    for market in markets:
        if not isinstance(market, dict):
            continue
        raw = {**market}
        raw.setdefault("events", [event_stub])
        raw.setdefault("tags", event.get("tags"))
        raw.setdefault("series", event.get("series"))
        raw.setdefault("image", event.get("image") or event.get("icon"))
        raw.setdefault("icon", event.get("icon") or event.get("image"))
        enriched.append(raw)
    return enriched


async def fetch_filtered_markets() -> list[MonitorMarket]:
    now = datetime.now(UTC)
    if settings.use_mock_data:
        return [market for raw in mock_gamma_markets() if (market := normalize_market(raw, now))]

    markets_by_id: dict[str, MonitorMarket] = {}
    limit = 100
    async with httpx.AsyncClient() as client:
        (
            markets_pages,
            events_pages,
            offset_markets_pages,
            offset_events_pages,
            finance_events,
            sports_events,
            crypto_events,
            weather_events,
        ) = await asyncio.gather(
            _fetch_keyset_pages(client, "markets", now, limit),
            _fetch_keyset_pages(client, "events", now, limit),
            _fetch_offset_pages(client, "markets", now, limit),
            _fetch_offset_pages(client, "events", now, limit),
            _fetch_finance_daily_events(client, now),
            _fetch_sports_supplement_events(client, now),
            _fetch_crypto_15m_events(client, now),
            _fetch_weather_supplement_events(client, now),
        )

    for page in markets_pages:
        for raw in page:
            if market := normalize_market(raw, now):
                if _within_discovery_horizon(market, now):
                    markets_by_id[market.market_id] = market

    for page in events_pages:
        for raw in (market for event in page for market in _event_markets(event)):
            if market := normalize_market(raw, now):
                if _within_discovery_horizon(market, now):
                    markets_by_id[market.market_id] = market

    for page in offset_markets_pages:
        for raw in page:
            if market := normalize_market(raw, now):
                if _within_discovery_horizon(market, now):
                    markets_by_id[market.market_id] = market

    for page in offset_events_pages:
        for raw in (market for event in page for market in _event_markets(event)):
            if market := normalize_market(raw, now):
                if _within_discovery_horizon(market, now):
                    markets_by_id[market.market_id] = market

    for event in finance_events:
        for raw in _event_markets(event):
            if market := normalize_market(raw, now):
                if _within_discovery_horizon(market, now):
                    markets_by_id[market.market_id] = market

    for event in sports_events:
        for raw in _event_markets(event):
            if market := normalize_market(raw, now):
                if _within_discovery_horizon(market, now) or _is_active_sports_supplement(market, now):
                    markets_by_id[market.market_id] = market

    for event in crypto_events:
        for raw in _event_markets(event):
            if market := normalize_market(raw, now):
                if _within_discovery_horizon(market, now):
                    markets_by_id[market.market_id] = market

    for event in weather_events:
        for raw in _event_markets(event):
            if market := normalize_market(raw, now):
                if _within_discovery_horizon(market, now):
                    markets_by_id[market.market_id] = market

    return sorted(markets_by_id.values(), key=lambda market: _candidate_sort_key(market, now))[: settings.max_filtered_markets]


async def _fetch_finance_daily_events(client: httpx.AsyncClient, now: datetime) -> list[dict]:
    local_date = now.astimezone(ET).date()
    dates = [local_date]
    if now.astimezone(ET).hour >= 16:
        dates.append(local_date + timedelta(days=1))
    tasks = []
    for date in dates:
        suffix = f"{date.strftime('%B').lower()}-{date.day}-{date.year}"
        for ticker in FINANCE_DAILY_TICKERS:
            tasks.append(_fetch_event_by_slug_with_retry(client, f"{ticker}-up-or-down-on-{suffix}"))
    rows = await asyncio.gather(*tasks, return_exceptions=True)
    return [row for row in rows if isinstance(row, dict)]


async def _fetch_crypto_15m_events(client: httpx.AsyncClient, now: datetime) -> list[dict]:
    current_start = int(now.timestamp()) // (15 * 60) * (15 * 60)
    starts = range(current_start - 15 * 60, current_start + 2 * 60 * 60 + 1, 15 * 60)
    tasks = [
        _fetch_event_by_slug_with_retry(client, f"{ticker}-updown-15m-{start}")
        for ticker in CRYPTO_15M_TICKERS
        for start in starts
    ]
    rows = await asyncio.gather(*tasks, return_exceptions=True)
    return [row for row in rows if isinstance(row, dict)]


async def _fetch_sports_supplement_events(client: httpx.AsyncClient, now: datetime) -> list[dict]:
    params = {
        "limit": "100",
        "active": "true",
        "closed": "false",
        "end_date_min": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "end_date_max": (now + timedelta(days=8)).isoformat().replace("+00:00", "Z"),
    }
    tasks = [_fetch_events_by_tag_with_retry(client, tag_id, params) for tag_id in SPORT_SUPPLEMENT_TAG_IDS]
    tasks.append(_fetch_soccer_supplement_events(client, now))
    pages = await asyncio.gather(*tasks, return_exceptions=True)
    events: dict[str, dict] = {}
    for page in pages:
        if isinstance(page, list):
            for event in page:
                if isinstance(event, dict) and event.get("id"):
                    events[str(event["id"])] = event
    return list(events.values())


async def _fetch_weather_supplement_events(client: httpx.AsyncClient, now: datetime) -> list[dict]:
    params = {
        "limit": "100",
        "active": "true",
        "closed": "false",
        "end_date_min": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "end_date_max": (now + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
    }
    return await _fetch_events_by_tag_with_retry(client, WEATHER_SUPPLEMENT_TAG_ID, params)


async def _fetch_soccer_supplement_events(client: httpx.AsyncClient, now: datetime) -> list[dict]:
    params = {
        "limit": "100",
        "active": "true",
        "closed": "false",
        "end_date_min": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "end_date_max": (now + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
    }
    tasks = [
        _fetch_events_by_tag_with_retry(client, SOCCER_SUPPLEMENT_TAG_ID, {**params, "offset": str(offset)})
        for offset in SOCCER_SUPPLEMENT_OFFSETS
    ]
    pages = await asyncio.gather(*tasks, return_exceptions=True)
    events: dict[str, dict] = {}
    for page in pages:
        if isinstance(page, list):
            for event in page:
                if isinstance(event, dict) and event.get("id"):
                    events[str(event["id"])] = event
    return list(events.values())


async def _fetch_events_by_tag_with_retry(client: httpx.AsyncClient, tag_id: str, params: dict[str, str]) -> list[dict]:
    request_params = {**params, "tag_id": tag_id}
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = await client.get(
                f"{settings.gamma_api_url.rstrip('/')}/events",
                params=request_params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else data.get("events") or data.get("data") or []
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            await asyncio.sleep(0.3 * (attempt + 1))
    if last_error:
        return []
    return []


async def _fetch_event_by_slug_with_retry(client: httpx.AsyncClient, slug: str) -> dict | None:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = await client.get(
                f"{settings.gamma_api_url.rstrip('/')}/events/slug/{slug}",
                timeout=12,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) and data.get("markets") else None
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            await asyncio.sleep(0.25 * (attempt + 1))
    if last_error:
        return None
    return None


async def _fetch_keyset_pages(client: httpx.AsyncClient, endpoint: str, now: datetime, limit: int) -> list[list[dict]]:
    pages: list[list[dict]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    seen_page_keys: set[tuple[str, ...]] = set()
    for _ in range(settings.gamma_max_pages):
        page, cursor = await _fetch_keyset_page_with_retry(client, endpoint, cursor, now, limit)
        page_key = tuple(str(row.get("id") or row.get("conditionId") or row.get("slug") or index) for index, row in enumerate(page))
        if page_key in seen_page_keys:
            break
        seen_page_keys.add(page_key)
        pages.append(page)
        if not cursor or len(page) < limit:
            break
        if cursor in seen_cursors:
            break
        seen_cursors.add(cursor)
    return pages


async def _fetch_offset_pages(client: httpx.AsyncClient, endpoint: str, now: datetime, limit: int) -> list[list[dict]]:
    tasks = [
        _fetch_offset_page_with_retry(client, endpoint, now, page_index * limit, limit)
        for page_index in range(settings.gamma_max_pages)
    ]
    rows = await asyncio.gather(*tasks, return_exceptions=True)
    pages: list[list[dict]] = []
    for row in rows:
        if isinstance(row, list) and row:
            pages.append(row)
    return pages


async def _fetch_offset_page_with_retry(
    client: httpx.AsyncClient,
    endpoint: str,
    now: datetime,
    offset: int,
    limit: int,
) -> list[dict]:
    params = {
        "active": "true",
        "closed": "false",
        "limit": str(limit),
        "offset": str(offset),
        "order": "endDate",
        "ascending": "true",
        **_window_params(now),
    }
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = await client.get(
                f"{settings.gamma_api_url.rstrip('/')}/{endpoint}",
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                rows = data.get(endpoint) or data.get("data") or []
                return rows if isinstance(rows, list) else []
            return data if isinstance(data, list) else []
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            await asyncio.sleep(0.3 * (attempt + 1))
    if last_error:
        return []
    return []


async def _fetch_keyset_page_with_retry(
    client: httpx.AsyncClient,
    endpoint: str,
    cursor: str | None,
    now: datetime,
    limit: int,
) -> tuple[list[dict], str | None]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return await fetch_gamma_keyset_page(client, endpoint, cursor, now, limit)
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            await asyncio.sleep(0.4 * (attempt + 1))
    if last_error:
        return [], None
    return [], None


def _candidate_sort_key(market: MonitorMarket, now: datetime) -> tuple[int, int, float, int]:
    deadline = _scan_deadline(market)
    remaining = int((deadline - now).total_seconds()) if deadline else 10**12
    remaining = max(0, remaining)
    liquidity = market.liquidity or 0
    probability = max(market.outcomePrices or [0])
    if market.kind == "crypto" and remaining <= 3600:
        lane_rank = 0
    elif market.kind in {"sports", "esports"} and remaining <= 6 * 3600:
        lane_rank = 1
    elif remaining <= 24 * 3600:
        lane_rank = 2
    else:
        lane_rank = 3
    liquidity_rank = 0 if liquidity >= 10_000 else 1 if liquidity >= 1_000 else 2 if liquidity >= 250 else 3
    return lane_rank, liquidity_rank, -probability, remaining


def _within_discovery_horizon(market: MonitorMarket, now: datetime) -> bool:
    if market.kind in {"sports", "esports"} and market.game_start_time:
        return (
            now - timedelta(hours=_market_live_window_hours(market)) <= market.game_start_time
            and market.game_start_time - now <= timedelta(hours=settings.discovery_horizon_hours)
        )
    deadline = _scan_deadline(market)
    if not deadline:
        return False
    if market.kind == "general" and not market.closed and market.active:
        if 0 <= (deadline - now).total_seconds() <= settings.discovery_horizon_hours * 3600:
            return True
        return _allows_general_settlement_grace(
            {
                "question": market.question,
                "tags": market.tags,
                "category": market.category,
                "seriesTicker": market.category,
            }
        ) and -timedelta(hours=GENERAL_SETTLEMENT_GRACE_HOURS) <= deadline - now <= timedelta(seconds=0)
    return timedelta(seconds=0) <= deadline - now <= timedelta(hours=settings.discovery_horizon_hours)


def _is_active_sports_supplement(market: MonitorMarket, now: datetime) -> bool:
    if market.kind not in {"sports", "esports"}:
        return False
    if not market.game_start_time:
        return False
    live_window = timedelta(hours=_market_live_window_hours(market))
    lookahead = timedelta(hours=SPORTS_LOOKAHEAD_HOURS)
    if not now - live_window <= market.game_start_time <= now + lookahead:
        return False
    probability = market.gamma_probability or max(market.outcomePrices or [0])
    return settings.high_probability_threshold <= probability <= 1 and (market.liquidity or 0) >= 250


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


def _market_live_window_hours(market: MonitorMarket) -> float:
    return SPORTS_LIVE_WINDOW_HOURS


async def fetch_hot_crypto_markets() -> list[MonitorMarket]:
    now = datetime.now(UTC)
    markets: dict[str, MonitorMarket] = {}
    limit = 100
    cursor: str | None = None
    async with httpx.AsyncClient() as client:
        crypto_events_task = asyncio.create_task(_fetch_crypto_15m_events(client, now))
        for _ in range(settings.crypto_hot_pages):
            page, cursor = await _fetch_keyset_page_with_retry(client, "markets", cursor, now, limit)
            for raw in page:
                if market := normalize_market(raw, now):
                    if market.kind == "crypto" and _within_discovery_horizon(market, now):
                        markets[market.market_id] = market
            if not cursor or len(page) < limit:
                break
        crypto_events = await crypto_events_task
        for raw in (market for event in crypto_events for market in _event_markets(event)):
            if market := normalize_market(raw, now):
                if market.kind == "crypto" and _within_discovery_horizon(market, now):
                    markets[market.market_id] = market
    return list(markets.values())


def _page_starts_after_horizon(items: list[dict], now: datetime) -> bool:
    horizon = now + timedelta(hours=settings.discovery_horizon_hours)
    dates = [_parse_dt(item.get("endDate") or item.get("end_date")) for item in items]
    dates = [date for date in dates if date]
    return bool(dates and min(dates) > horizon)
