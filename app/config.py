from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Pydantic validates every field on startup — if a required
    variable is missing the app refuses to start with a clear error.
    """

    # ── Supabase ──────────────────────────────────────────────────────────
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # ── App ───────────────────────────────────────────────────────────────
    app_name: str = "BackendFinance API"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── CORS ──────────────────────────────────────────────────────────────
    # Pydantic automatically splits comma-separated string into a List
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def allowed_origins_list(self) -> List[str]:
        """
        Splits comma-separated origins string into a list.
        Strips whitespace from each entry to handle accidental spaces.
        e.g. "http://a.com, http://b.com" → ["http://a.com", "http://b.com"]
        """
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    # ── Exchange Rate API ─────────────────────────────────────────────────
    exchange_rate_api_key: str = ""
    exchange_rate_base_currency: str = "MXN"

    model_config = SettingsConfigDict(
        # Tells pydantic-settings where to find the .env file
        env_file=".env",
        # Ignore extra variables in .env that are not defined here
        extra="ignore",
        # Case insensitive — SUPABASE_URL and supabase_url both work
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.

    @lru_cache ensures .env is only read once per process lifetime
    instead of on every request that calls get_settings().
    FastAPI dependency injection calls this function per request
    without the cache this would re-read .env thousands of times.
    """
    return Settings()


# Module-level singleton for direct imports
# Use this when you need settings outside of FastAPI dependency injection
settings = get_settings()