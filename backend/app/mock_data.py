from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def mock_gamma_markets() -> list[dict]:
    now = datetime.now(UTC)
    base_markets = [
        {
            "id": "mock-btc-70k",
            "question": "Will BTC price be above $70,000 on May 25?",
            "endDate": (now + timedelta(minutes=24)).isoformat(),
            "active": True,
            "closed": False,
            "tags": [{"label": "Crypto"}, {"label": "BTC"}],
            "series": [{"ticker": "BTC"}],
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.925","0.075"]',
            "clobTokenIds": '["btc-yes-token","btc-no-token"]',
        },
        {
            "id": "mock-celtics-heat",
            "question": "NBA: Celtics vs Heat Match Winner",
            "endDate": (now + timedelta(hours=3)).isoformat(),
            "active": True,
            "closed": False,
            "sports_market_type": "moneyline",
            "game_start_time": (now - timedelta(minutes=86)).isoformat(),
            "tags": [{"label": "Sports"}, {"label": "NBA"}],
            "outcomes": '["Celtics","Heat"]',
            "outcomePrices": '["0.913","0.087"]',
            "clobTokenIds": '["celtics-token","heat-token"]',
        },
        {
            "id": "mock-eth-3800",
            "question": "Will ETH price be above $3,800 in next 2 hours?",
            "endDate": (now + timedelta(minutes=65)).isoformat(),
            "active": True,
            "closed": False,
            "tags": [{"label": "Crypto"}, {"label": "ETH"}],
            "series": [{"ticker": "ETH"}],
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.931","0.069"]',
            "clobTokenIds": '["eth-yes-token","eth-no-token"]',
        },
        {
            "id": "mock-lakers-warriors",
            "question": "Will the Lakers win vs Warriors?",
            "endDate": (now + timedelta(hours=4)).isoformat(),
            "active": True,
            "closed": False,
            "sports_market_type": "win",
            "game_start_time": (now - timedelta(minutes=58)).isoformat(),
            "tags": [{"label": "Sports"}, {"label": "NBA"}],
            "outcomes": '["Lakers","Warriors"]',
            "outcomePrices": '["0.902","0.098"]',
            "clobTokenIds": '["lakers-token","warriors-token"]',
        },
        {
            "id": "mock-rangers-devils",
            "question": "NHL: Rangers vs Devils Match Winner",
            "endDate": (now - timedelta(minutes=12)).isoformat(),
            "active": True,
            "closed": True,
            "sports_market_type": "moneyline",
            "game_start_time": (now - timedelta(hours=2, minutes=10)).isoformat(),
            "tags": [{"label": "Sports"}, {"label": "NHL"}],
            "outcomes": '["Rangers","Devils"]',
            "outcomePrices": '["0.885","0.115"]',
            "clobTokenIds": '["rangers-token","devils-token"]',
        },
    ]

    crypto_specs = [
        ("mock-btc-72k", "Will BTC price be above $72,000 in next 2 hours?", "BTC", 51, 0.918),
        ("mock-btc-68k", "Will BTC price stay above $68,000 this hour?", "BTC", 39, 0.941),
        ("mock-eth-4000", "Will ETH price be above $4,000 in next 2 hours?", "ETH", 93, 0.904),
        ("mock-eth-3600", "Will ETH price stay above $3,600 this hour?", "ETH", 34, 0.956),
        ("mock-sol-200", "Will SOL price be above $200 on May 25?", "SOL", 44, 0.918),
        ("mock-sol-185", "Will SOL price stay above $185 in next 2 hours?", "SOL", 112, 0.907),
        ("mock-btc-spot-up", "Will BTC close the hour higher than it opened?", "BTC", 58, 0.912),
        ("mock-eth-spot-up", "Will ETH close the hour higher than it opened?", "ETH", 73, 0.921),
    ]
    for market_id, question, ticker, minutes, yes_price in crypto_specs:
        base_markets.append(
            {
                "id": market_id,
                "question": question,
                "endDate": (now + timedelta(minutes=minutes)).isoformat(),
                "active": True,
                "closed": False,
                "tags": [{"label": "Crypto"}, {"label": ticker}],
                "series": [{"ticker": ticker}],
                "outcomes": '["Yes","No"]',
                "outcomePrices": f'["{yes_price:.3f}","{1 - yes_price:.3f}"]',
                "clobTokenIds": f'["{market_id}-yes-token","{market_id}-no-token"]',
            }
        )

    sports_specs = [
        ("mock-knicks-bucks", "Will the Knicks win vs Bucks?", "NBA", "win", -42, 0.914),
        ("mock-dodgers-giants", "MLB: Dodgers vs Giants Match Winner", "MLB", "moneyline", -88, 0.922),
        ("mock-yankees-redsox", "MLB: Yankees vs Red Sox Match Winner", "MLB", "moneyline", 28, 0.906),
        ("mock-chiefs-raiders", "NFL: Chiefs vs Raiders Match Winner", "NFL", "moneyline", 64, 0.918),
        ("mock-arsenal-chelsea", "Soccer: Arsenal vs Chelsea Match Winner", "Soccer", "moneyline", -77, 0.903),
        ("mock-ufc-main-event", "UFC: Main Event Winner", "UFC", "moneyline", 92, 0.934),
        ("mock-tennis-final", "Tennis: Final Match Winner", "Tennis", "moneyline", -22, 0.916),
        ("mock-nhl-bruins-leafs", "NHL: Bruins vs Maple Leafs Match Winner", "NHL", "moneyline", 118, 0.905),
    ]
    for market_id, question, sport, market_type, start_offset, yes_price in sports_specs:
        base_markets.append(
            {
                "id": market_id,
                "question": question,
                "endDate": (now + timedelta(hours=3, minutes=abs(start_offset) % 40)).isoformat(),
                "active": True,
                "closed": False,
                "sports_market_type": market_type,
                "game_start_time": (now + timedelta(minutes=start_offset)).isoformat(),
                "tags": [{"label": "Sports"}, {"label": sport}],
                "outcomes": '["Yes","No"]',
                "outcomePrices": f'["{yes_price:.3f}","{1 - yes_price:.3f}"]',
                "clobTokenIds": f'["{market_id}-yes-token","{market_id}-no-token"]',
            }
        )

    return base_markets
