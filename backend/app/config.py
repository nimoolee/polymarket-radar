from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    use_mock_data: bool = True
    gamma_api_url: str = "https://gamma-api.polymarket.com"
    clob_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    clob_api_url: str = "https://clob.polymarket.com"
    poll_interval_seconds: int = 180
    clob_scan_interval_seconds: int = 30
    crypto_poll_interval_seconds: int = 60
    crypto_hot_pages: int = 3
    discovery_horizon_hours: int = 48
    price_move_threshold: float = 0.015
    frontend_event_buffer: int = 200
    gamma_max_pages: int = 12
    max_filtered_markets: int = 2500
    high_probability_threshold: float = 0.80
    clob_max_tokens: int = 300
    clob_orderbook_check_limit: int = 300
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    scanning_enabled_default: bool = False

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")


settings = Settings()
