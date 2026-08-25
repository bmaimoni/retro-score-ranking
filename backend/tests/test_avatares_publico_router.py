"""
Testes de routers/avatares_publico.py — GET /api/avatares, sem auth.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


@pytest.mark.asyncio
async def test_listar_avatares_publico_sem_auth(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    avatares = [{"id": make_uuid(), "nome": "Robô", "url": "https://cdn/robo.png"}]

    with patch("repositories.avatar.listar_ativos", AsyncMock(return_value=avatares)):
        resp = await client.get("/api/avatares")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
