"""
Testes do router público de placares — /api/p/{slug}/...
Ver docs/EVENTOS_SPEC.md §3-4.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


def _placar_global():
    return {"id": make_uuid(), "nome": "Hall da Fama Geral", "slug": "geral", "escopo": "global"}


def _placar_customizado():
    return {"id": make_uuid(), "nome": "Temporada 2026", "slug": "temporada-2026", "escopo": "customizado"}


def _jogo():
    return {"id": make_uuid(), "nome": "Pac-Man", "slug": "pac-man", "score_max": 999990}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


# ── Placar inexistente ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_placar_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.get("/api/p/nao-existe/ranking/pac-man")

    assert resp.status_code == 404


# ── Ranking por placar ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ranking_placar_global_sem_filtro_de_evento(client):
    """
    Placar global: a query não filtra por evento (repositories.placar.listar_ranking
    decide isso sozinha) — o teste garante que o router repassa o placar certo
    e devolve o que o repository retornar.
    """
    placar = _placar_global()
    jogo   = _jogo()
    entradas = [
        {"id": make_uuid(), "nick": "A", "pontuacao": 99000, "evento_id": make_uuid()},
        {"id": make_uuid(), "nick": "B", "pontuacao": 88000, "evento_id": make_uuid()},
    ]
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_slug", AsyncMock(return_value=placar)), \
         patch("repositories.jogo.buscar_por_slug",   AsyncMock(return_value=jogo)), \
         patch("repositories.placar.listar_ranking",  AsyncMock(return_value=entradas)) as listar_mock:
        resp = await client.get("/api/p/geral/ranking/pac-man")

    assert resp.status_code == 200
    data = resp.json()
    assert data["placar"] == "geral"
    assert len(data["entradas"]) == 2
    # Garante que o placar (com escopo) foi repassado ao repository
    listar_mock.assert_called_once_with(pool, jogo["id"], placar)


@pytest.mark.asyncio
async def test_ranking_placar_customizado(client):
    placar = _placar_customizado()
    jogo   = _jogo()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_slug", AsyncMock(return_value=placar)), \
         patch("repositories.jogo.buscar_por_slug",   AsyncMock(return_value=jogo)), \
         patch("repositories.placar.listar_ranking",  AsyncMock(return_value=[])):
        resp = await client.get("/api/p/temporada-2026/ranking/pac-man")

    assert resp.status_code == 200
    assert resp.json()["placar"] == "temporada-2026"


@pytest.mark.asyncio
async def test_ranking_placar_jogo_inexistente_retorna_404(client):
    placar = _placar_global()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_slug", AsyncMock(return_value=placar)), \
         patch("repositories.jogo.buscar_por_slug",   AsyncMock(return_value=None)):
        resp = await client.get("/api/p/geral/ranking/nao-existe")

    assert resp.status_code == 404


# ── Líderes do placar ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lideres_placar_retorna_top1_por_jogo(client):
    placar = _placar_global()
    lideres = {make_uuid(): {"slug": "pac-man", "nick": "CAMPEAO", "pontuacao": 99000}}
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_slug", AsyncMock(return_value=placar)), \
         patch("repositories.placar.listar_lideres",  AsyncMock(return_value=lideres)):
        resp = await client.get("/api/p/geral/ranking/lideres")

    assert resp.status_code == 200
    assert list(resp.json().values())[0]["nick"] == "CAMPEAO"


@pytest.mark.asyncio
async def test_rota_lideres_nao_e_capturada_como_jogo_slug(client):
    """
    Regressão da armadilha já documentada em SPEC.md §8: /ranking/lideres
    precisa ser resolvida pela rota específica, não pela genérica
    /ranking/{jogo_slug} tratando 'lideres' como se fosse um jogo.
    """
    placar = _placar_global()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_slug", AsyncMock(return_value=placar)), \
         patch("repositories.placar.listar_lideres",  AsyncMock(return_value={})) as lideres_mock, \
         patch("repositories.jogo.buscar_por_slug",   AsyncMock(return_value=None)) as jogo_mock:
        resp = await client.get("/api/p/geral/ranking/lideres")

    assert resp.status_code == 200
    lideres_mock.assert_called_once()
    jogo_mock.assert_not_called()


# ── Repository: SQL muda de verdade entre global e customizado ────────────────

@pytest.mark.asyncio
async def test_repository_ranking_global_nao_filtra_evento(fake_pool):
    import repositories.placar as placar_repo

    fake_pool.set_fetch([])
    placar = _placar_global()

    await placar_repo.listar_ranking(fake_pool, "jogo-id", placar)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "placar_eventos" not in sql
    assert "evento_id" not in sql or "IN (SELECT evento_id" not in sql


@pytest.mark.asyncio
async def test_repository_ranking_customizado_filtra_por_placar_eventos(fake_pool):
    import repositories.placar as placar_repo

    fake_pool.set_fetch([])
    placar = _placar_customizado()

    await placar_repo.listar_ranking(fake_pool, "jogo-id", placar)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "placar_eventos" in sql
    assert "WHERE placar_id = $2" in sql
    # jogo_id e placar_id são os dois parâmetros posicionais
    assert fake_pool.fetch.call_args[0][1:] == ("jogo-id", placar["id"])


@pytest.mark.asyncio
async def test_repository_lideres_global_vs_customizado_sql_diferente(fake_pool):
    import repositories.placar as placar_repo

    fake_pool.set_fetch([])
    await placar_repo.listar_lideres(fake_pool, _placar_global())
    sql_global = " ".join(fake_pool.fetch.call_args[0][0].split())

    fake_pool.set_fetch([])
    await placar_repo.listar_lideres(fake_pool, _placar_customizado())
    sql_customizado = " ".join(fake_pool.fetch.call_args[0][0].split())

    assert "placar_eventos" not in sql_global
    assert "placar_eventos" in sql_customizado
