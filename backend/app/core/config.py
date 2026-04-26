"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/trading_ai"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Exchange APIs
    BINANCE_API_KEY: str = ""
    BINANCE_SECRET: str = ""

    # Data Sources
    WHALE_ALERT_API_KEY: str = ""
    GLASSNODE_API_KEY: str = ""

    # Social Media
    TWITTER_BEARER_TOKEN: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""

    # AI Chat
    ANTHROPIC_API_KEY: str = ""

    # Notifications
    TELEGRAM_BOT_TOKEN: str = ""

    # Risk Settings
    MAX_DRAWDOWN_PCT: float = 10.0
    RISK_PER_TRADE_PCT: float = 1.5
    MIN_SIGNAL_CONFIDENCE: float = 50.0

    # App
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    CORS_ORIGINS: str = "http://localhost:5173"

    # Auth (simple env-based credentials for the token endpoint)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
    )

    def validate_production(self) -> list[str]:
        """Check for insecure defaults and missing keys in production."""
        warnings: list[str] = []
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == "change-me-in-production":
                warnings.append("SECRET_KEY is still the default — rotate immediately!")
            if self.ADMIN_PASSWORD == "admin":
                warnings.append("ADMIN_PASSWORD is still 'admin' — change before go-live!")
            if not self.ANTHROPIC_API_KEY:
                warnings.append("ANTHROPIC_API_KEY not set — AI chat disabled")
            if not self.BINANCE_API_KEY:
                warnings.append("BINANCE_API_KEY not set — live market data may be rate-limited")
            if not self.TELEGRAM_BOT_TOKEN:
                warnings.append("TELEGRAM_BOT_TOKEN not set — Telegram notifications disabled")
            if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
                warnings.append("DATABASE_URL points to localhost in production")
        return warnings

    def enforce_production_security(self) -> None:
        """Raise RuntimeError for critical insecure defaults in production.

        Called during application lifespan startup. Non-fatal warnings are
        returned by ``validate_production()`` and logged; fatal ones are raised
        here so the container exits cleanly rather than serving with broken config.
        """
        if self.ENVIRONMENT != "production":
            return
        fatal: list[str] = []
        if self.SECRET_KEY == "change-me-in-production":
            fatal.append("SECRET_KEY must be changed before running in production")
        if self.ADMIN_PASSWORD == "admin":
            fatal.append("ADMIN_PASSWORD must be changed before running in production")
        if fatal:
            raise RuntimeError(
                "Production security checks failed:\n" + "\n".join(f"  • {f}" for f in fatal)
            )

    def enforce_production_security(self) -> None:
        """Raise RuntimeError if critical settings use default values in production.

        This method should be called during application startup to prevent
        deploying with insecure defaults.
        """
        if self.ENVIRONMENT != "production":
            return

        errors: list[str] = []

        if self.SECRET_KEY == "change-me-in-production":
            errors.append(
                "SECRET_KEY is still the default value. "
                "Set a strong, unique SECRET_KEY for production."
            )

        if self.DATABASE_URL == "postgresql+asyncpg://user:pass@localhost:5432/trading_ai":
            errors.append(
                "DATABASE_URL is still the default value. "
                "Configure a production database connection string."
            )

        if self.REDIS_URL == "redis://localhost:6379/0":
            errors.append(
                "REDIS_URL is still the default value. "
                "Configure a production Redis connection string."
            )

        if errors:
            raise RuntimeError(
                "Production security check failed:\n- " + "\n- ".join(errors)
            )


settings = Settings()
