import os
import pytest

BASE_URL     = os.getenv("SMOKE_BASE_URL",     "https://retro-score-ranking.vercel.app")
API_URL      = os.getenv("SMOKE_API_URL",      "https://retro-score-ranking-production.up.railway.app")
ADMIN_SECRET = os.getenv("SMOKE_ADMIN_SECRET", "")
DEFAULT_TIMEOUT = 15_000


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def api_url():
    return API_URL


@pytest.fixture(scope="session")
def admin_secret():
    if not ADMIN_SECRET:
        pytest.skip("SMOKE_ADMIN_SECRET nao definido — smoke tests de admin ignorados")
    return ADMIN_SECRET