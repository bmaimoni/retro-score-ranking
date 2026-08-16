"""
Testes do router público de telões — /api/teloes/{slug}/config.
Ver docs/EVENTOS_SPEC.md §3-5.
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
async def test_telao_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_config_por_slug", AsyncMock(return_value=None)):
        resp = await client.get("/api/teloes/nao-existe/config")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_telao_de_placar_retorna_config_completa(client):
    """Telão apontando pra um placar (ex.: Hall da Fama Geral)."""
    config = {
        "nome": "Hall da Fama Geral",
        "slug": "geral",
        "top_n": 10,
        "evento_slug": None,
        "placar_slug": "geral",
        "jogos": [
            {"nome": "Donkey Kong", "slug": "donkey-kong", "ordem": 0},
            {"nome": "Galaga",      "slug": "galaga",      "ordem": 1},
        ],
    }
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_config_por_slug", AsyncMock(return_value=config)):
        resp = await client.get("/api/teloes/geral/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["top_n"] == 10
    assert data["placar_slug"] == "geral"
    assert data["evento_slug"] is None
    assert len(data["jogos"]) == 2
    assert data["jogos"][0]["slug"] == "donkey-kong"


@pytest.mark.asyncio
async def test_telao_de_evento_retorna_config_completa(client):
    """Telão apontando pra um evento específico (não um placar)."""
    config = {
        "nome": "Telão Entrada Principal",
        "slug": "entrada-principal",
        "top_n": 5,
        "evento_slug": "canal3expo",
        "placar_slug": None,
        "jogos": [{"nome": "Pac-Man", "slug": "pac-man", "ordem": 0}],
    }
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_config_por_slug", AsyncMock(return_value=config)):
        resp = await client.get("/api/teloes/entrada-principal/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["evento_slug"] == "canal3expo"
    assert data["placar_slug"] is None
    assert data["top_n"] == 5


# ── Repository: SQL monta jogos ordenados e só ativos ─────────────────────────

@pytest.mark.asyncio
async def test_repository_busca_apenas_jogos_ativos_do_telao():
    """
    telao_jogos.ativo=false não deve aparecer na config — a query do
    repository filtra isso (ver repositories/telao.py).
    """
    import repositories.telao as telao_repo

    telao_row = {
        "id": make_uuid(), "nome": "Hall da Fama Geral", "slug": "geral",
        "top_n": 10, "evento_id": None, "evento_slug": None,
        "placar_id": make_uuid(), "placar_slug": "geral",
    }
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=telao_row)
    pool.fetch    = AsyncMock(return_value=[{"nome": "Pac-Man", "slug": "pac-man", "ordem": 0}])

    resultado = await telao_repo.buscar_config_por_slug(pool, "geral")

    assert resultado["nome"] == "Hall da Fama Geral"
    assert len(resultado["jogos"]) == 1
    # Confirma que a query de jogos filtra por ativo=true (checando a SQL enviada)
    sql_jogos = pool.fetch.call_args[0][0]
    assert "tj.ativo    = true" in sql_jogos or "ativo = true" in " ".join(sql_jogos.split())


@pytest.mark.asyncio
async def test_repository_retorna_none_para_slug_inexistente():
    import repositories.telao as telao_repo

    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)

    resultado = await telao_repo.buscar_config_por_slug(pool, "nao-existe")

    assert resultado is None
