"""
Configuração dos testes smoke E2E.

Variáveis de ambiente necessárias:
  SMOKE_BASE_URL   — URL do frontend (ex: https://retro-score-ranking.vercel.app)
  SMOKE_API_URL    — URL da API     (ex: https://retro-score-ranking-production.up.railway.app)
  SMOKE_ADMIN_SECRET — senha do admin

Rodar com:
  pytest tests/smoke/ -v --headed   # com browser visível
  pytest tests/smoke/ -v            # headless
"""
import os
import pytest
from playwright.sync_api import Page, expect

BASE_URL     = os.getenv("SMOKE_BASE_URL",    "https://retro-score-ranking.vercel.app")
API_URL      = os.getenv("SMOKE_API_URL",     "https://retro-score-ranking-production.up.railway.app")
ADMIN_SECRET = os.getenv("SMOKE_ADMIN_SECRET", "")

# Timeout padrão generoso para redes externas
DEFAULT_TIMEOUT = 15_000  # 15s


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL

@pytest.fixture(scope="session")
def api_url():
    return API_URL

@pytest.fixture(scope="session")
def admin_secret():
    if not ADMIN_SECRET:
        pytest.skip("SMOKE_ADMIN_SECRET não definido — smoke tests de admin ignorados")
    return ADMIN_SECRET
