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
        """Check for insecure defaults in production."""
        warnings: list[str] = []
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == "change-me-in-production":
                warnings.append("SECRET_KEY is still the default!")
            if not self.ANTHROPIC_API_KEY:
                warnings.append("ANTHROPIC_API_KEY not set")
        return warnings

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
