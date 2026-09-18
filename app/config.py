from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/app.db"
    host: str = "0.0.0.0"
    port: int = 8000
    # Comma-separated origins, or * for any origin without credentials.
    cors_origins: str = "*"


settings = Settings()
