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
    rate_limit: int = 10
    rate_window_seconds: int = 3600

    # CORS
    allowed_origins: str = "http://localhost:3000"

    # Ambiente
    environment: str = "development"

    # Autenticação — Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # Autenticação — Magic Link (Resend)
    resend_api_key: str = ""
    resend_from_email: str = "login@canal3.com.br"
    magic_link_ttl_minutes: int = 15

    # Autenticação — Sessão
    session_cookie_name: str = "canal3_session"
    session_ttl_days: int = 30

    # URL base do frontend, para redirecionar de volta após login
    frontend_base_url: str = "https://retro-score-ranking.vercel.app"

    @property
    def auth_configurado(self) -> dict[str, bool]:
        """Quais provedores de login estão configurados (env vars presentes)."""
        return {
            "google": bool(
                self.google_client_id and self.google_client_secret and self.google_redirect_uri
            ),
            "magic_link": bool(self.resend_api_key),
        }

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()