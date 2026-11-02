from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _environment_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("PYON_HOST", "127.0.0.1")
    port: int = int(os.getenv("PYON_PORT", "8765"))
    mt5_terminal_path: str | None = os.getenv("PYON_MT5_TERMINAL_PATH") or None
    mt5_auto_start: bool = _environment_flag("PYON_MT5_AUTO_START", True)
    symbol: str | None = os.getenv("PYON_SYMBOL") or None
    quote_poll_seconds: float = float(os.getenv("PYON_QUOTE_POLL_SECONDS", "2"))
    research_poll_seconds: float = float(os.getenv("PYON_RESEARCH_POLL_SECONDS", "30"))
    research_bootstrap_retry_seconds: int = int(os.getenv("PYON_RESEARCH_BOOTSTRAP_RETRY_SECONDS", "21600"))
    training_interval_seconds: int = int(os.getenv("PYON_TRAINING_INTERVAL_SECONDS", "21600"))
    delayed_seconds: int = int(os.getenv("PYON_DELAYED_SECONDS", "5"))
    stale_seconds: int = int(os.getenv("PYON_STALE_SECONDS", "15"))
    calendar_url: str = os.getenv("PYON_CALENDAR_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    calendar_ttl_seconds: int = int(os.getenv("PYON_CALENDAR_TTL_SECONDS", "600"))
    official_macro_ttl_seconds: int = int(os.getenv("PYON_OFFICIAL_MACRO_TTL_SECONDS", "3600"))
    dxy_symbol: str | None = os.getenv("PYON_DXY_SYMBOL") or None
    us10y_symbol: str | None = os.getenv("PYON_US10Y_SYMBOL") or None
    wti_symbol: str | None = os.getenv("PYON_WTI_SYMBOL") or None
    volatility_symbol: str | None = os.getenv("PYON_VOLATILITY_SYMBOL") or None
    operator_token: str | None = os.getenv("PYON_OPERATOR_TOKEN") or None
    database_path: Path = PROJECT_ROOT / "data" / "pyontrading2.db"
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"


settings = Settings()

