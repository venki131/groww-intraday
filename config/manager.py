"""
Central Configuration Management System.

Loads settings from:
1. config/settings.yaml (base defaults)
2. .env file (environment overrides)
3. Actual environment variables (highest priority)

Usage:
    from config.manager import get_settings
    settings = get_settings()
    print(settings.broker.api_base_url)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class BrokerSettings(BaseSettings):
    """Groww broker configuration."""

    model_config = SettingsConfigDict(env_prefix="GROWW_", extra="ignore")

    api_key: str = Field(default="", description="Groww API key (from env)")
    api_secret: str = Field(default="", description="Groww API secret (from env)")
    client_id: str = Field(default="", description="Groww client ID (from env)")
    api_base_url: str = "https://api.groww.in/v1"
    ws_url: str = "wss://ws.groww.in/v1"
    exchange: str = "NSE"
    segment: str = "EQ"
    live_trading_enabled: bool = False   # Hardcoded safety guard
    paper_trading_enabled: bool = True
    request_timeout_sec: int = 30
    rate_limit_calls_per_minute: int = 60
    retry_max_attempts: int = 3
    retry_wait_seconds: int = 2

    @field_validator("live_trading_enabled", mode="before")
    @classmethod
    def block_live_trading(cls, v: Any) -> bool:
        """Live trading is permanently disabled."""
        return False


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""

    model_config = SettingsConfigDict(env_prefix="DB_", extra="ignore")

    host: str = Field(default="localhost", alias="DB_HOST")
    port: int = Field(default=5432, alias="DB_PORT")
    name: str = Field(default="groww_intraday", alias="DB_NAME")
    user: str = Field(default="postgres", alias="DB_USER")
    password: str = Field(default="", alias="DB_PASSWORD")
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 1800
    echo_sql: bool = False

    model_config = SettingsConfigDict(populate_by_name=True, extra="ignore")

    @property
    def async_url(self) -> str:
        """Async SQLAlchemy connection URL."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_url(self) -> str:
        """Sync SQLAlchemy connection URL (for Alembic)."""
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class TelegramSettings(BaseSettings):
    """Telegram notification configuration."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", extra="ignore")

    bot_token: str = Field(default="", description="Telegram bot token")
    chat_id: str = Field(default="", description="Telegram chat ID")
    enabled: bool = False


class RiskSettings(BaseSettings):
    """Risk management parameters."""

    model_config = SettingsConfigDict(extra="ignore")

    max_risk_per_trade_pct: float = 1.0
    max_open_positions: int = 3
    max_daily_loss_pct: float = 3.0
    max_position_size_pct: float = 20.0
    stop_loss_pct: float = 1.5
    take_profit_pct: float = 3.0
    trailing_stop_enabled: bool = True
    trailing_stop_pct: float = 1.0


class BacktestSettings(BaseSettings):
    """Backtesting engine parameters."""

    model_config = SettingsConfigDict(env_prefix="BACKTEST_", extra="ignore")

    start_date: str = "2023-01-01"
    end_date: str = "2023-12-31"
    commission_pct: float = 0.03
    slippage_pct: float = 0.01
    data_source: str = "csv"


class MarketSettings(BaseSettings):
    """Market / universe configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    exchange: str = "NSE"
    segment: str = "EQ"
    candle_interval_minutes: int = 5
    universe: str = "NIFTY100"
    market_open_time: str = "09:15"
    market_close_time: str = "15:30"
    avoid_first_minutes: int = 15
    avoid_last_minutes: int = 15


class TradingSettings(BaseSettings):
    """Core trading session parameters."""

    model_config = SettingsConfigDict(extra="ignore")

    initial_capital: float = Field(
        default=10000, description="Starting capital in INR"
    )
    currency: str = "INR"
    mode: str = "backtest"  # backtest | paper  (live is disabled)

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"backtest", "paper"}
        if str(v).lower() not in allowed:
            raise ValueError(
                f"Invalid mode '{v}'. Allowed: {allowed}. Live trading is disabled."
            )
        return str(v).lower()


class ApiSettings(BaseSettings):
    """FastAPI server configuration."""

    model_config = SettingsConfigDict(env_prefix="API_", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    workers: int = 1
    cors_origins: List[str] = ["http://localhost:8501", "http://localhost:3000"]


class LoggingSettings(BaseSettings):
    """Structured logging configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    level: str = "INFO"
    format: str = "json"
    log_file: str = "logs/app.log"
    rotation: str = "10 MB"
    retention: str = "7 days"


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """
    Root application settings.

    Loads in priority order:
      environment variables > .env file > settings.yaml defaults
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_debug: bool = False
    app_log_level: str = "INFO"
    secret_key: str = "change-me"

    # Composed sub-settings (loaded separately)
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    backtest: BacktestSettings = Field(default_factory=BacktestSettings)
    market: MarketSettings = Field(default_factory=MarketSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @classmethod
    def from_yaml(cls, yaml_path: Optional[Path] = None) -> "Settings":
        """
        Load settings merging YAML defaults with environment variables.

        Args:
            yaml_path: Path to settings.yaml. Defaults to config/settings.yaml.

        Returns:
            Fully populated Settings instance.
        """
        if yaml_path is None:
            yaml_path = Path(__file__).parent / "settings.yaml"

        yaml_data: dict[str, Any] = {}
        if yaml_path.exists():
            with open(yaml_path, "r") as fh:
                yaml_data = yaml.safe_load(fh) or {}

        # Flatten nested yaml sections into env-var-style keys where needed
        # Sub-models handle their own env_prefix; just pass top-level keys.
        return cls(**{k: v for k, v in yaml_data.get("application", {}).items()
                      if k in cls.model_fields})


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.

    Call ``get_settings.cache_clear()`` in tests to reset.
    """
    return Settings.from_yaml()