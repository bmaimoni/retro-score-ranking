from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Banco
    database_url: str

    # Supabase Storage
    supabase_url: str
    supabase_service_key: str
    storage_bucket: str = "fotos-ranking"

    # Segurança
    admin_secret: str
    ip_hash_salt: str

    # Rate limit
    rate_limit: int = 3
    rate_window_seconds: int = 3600

    # CORS
    allowed_origins: str = "http://localhost:3000"

    # Ambiente
    environment: str = "development"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
