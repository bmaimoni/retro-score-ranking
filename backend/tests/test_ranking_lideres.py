"""
Testes do endpoint GET /api/ranking/lideres
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_lideres_retorna_top1_por_game(client):
    game1 = make_uuid()
    game2 = make_uuid()
    rows = [
        {"game_id": game1, "slug": "pac-man",    "nick": "CAMPEAO", "pontuacao": 99000},
        {"game_id": game2, "slug": "river-raid", "nick": "ACE",     "pontuacao": 45000},
    ]
    pool_mock = MagicMock()
    pool_mock.fetch = AsyncMock(return_value=rows)

    app.dependency_overrides[get_pool] = lambda: pool_mock
    try:
        resp = await client.get("/api/ranking/lideres")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data[game1]["nick"] == "CAMPEAO"
    assert data[game1]["pontuacao"] == 99000
    assert data[game2]["slug"] == "river-raid"


@pytest.mark.asyncio
async def test_lideres_vazio_quando_sem_entries(client):
    pool_mock = MagicMock()
    pool_mock.fetch = AsyncMock(return_value=[])

    app.dependency_overrides[get_pool] = lambda: pool_mock
    try:
        resp = await client.get("/api/ranking/lideres")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_lideres_nao_conflita_com_rota_slug(client):
    pool_mock = MagicMock()
    pool_mock.fetch = AsyncMock(return_value=[])

    app.dependency_overrides[get_pool] = lambda: pool_mock
    try:
        resp = await client.get("/api/ranking/lideres")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "game" not in resp.json()