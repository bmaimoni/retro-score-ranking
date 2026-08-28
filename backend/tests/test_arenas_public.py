"""
Testes do router público de arenas — GET /api/arenas/com-event-ativo.
Ver docs/BACKLOG_2026.md §2 item 2.1: tela inicial sem ?event= na URL
(sem fallback hardcoded desde a Fase 6) precisa descobrir pra qual
arena/event mandar o visitante.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


def _arena(**overrides):
    base = {"id": make_uuid(), "nome": "Canal3", "slug": "canal3", "logo_url": None}
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


@pytest.mark.asyncio
async def test_lista_arenas_com_event_slug_resolvido(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena = _arena()

    with patch("repositories.arena.listar_com_event_ativo", AsyncMock(return_value=[arena])), \
         patch("repositories.event.buscar_event_envio_atual_da_arena",
               AsyncMock(return_value={"slug": "canal3expo-2026"})):
        resp = await client.get("/api/arenas/com-event-ativo")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["event_slug"] == "canal3expo-2026"
    assert data[0]["nome"] == "Canal3"


@pytest.mark.asyncio
async def test_lista_vazia_quando_nenhuma_arena_qualifica(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.listar_com_event_ativo", AsyncMock(return_value=[])):
        resp = await client.get("/api/arenas/com-event-ativo")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_arena_sem_event_resolvivel_fica_de_fora_sem_quebrar(client):
    """Defesa: se por algum motivo o resolver não achar event pra uma
    arena que passou no filtro da listagem (corrida entre as duas
    queries), a resposta não quebra — só omite essa arena."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_ok = _arena(nome="Canal3")
    arena_sem_event = _arena(nome="RetroExpo")

    with patch("repositories.arena.listar_com_event_ativo",
               AsyncMock(return_value=[arena_ok, arena_sem_event])), \
         patch("repositories.event.buscar_event_envio_atual_da_arena",
               AsyncMock(side_effect=[{"slug": "canal3expo"}, None])):
        resp = await client.get("/api/arenas/com-event-ativo")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["nome"] == "Canal3"


@pytest.mark.asyncio
async def test_multiplas_arenas_retorna_todas_resolvidas(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_a = _arena(nome="Canal3")
    arena_b = _arena(nome="RetroExpo")

    with patch("repositories.arena.listar_com_event_ativo",
               AsyncMock(return_value=[arena_a, arena_b])), \
         patch("repositories.event.buscar_event_envio_atual_da_arena",
               AsyncMock(side_effect=[{"slug": "canal3expo"}, {"slug": "retroexpo-2026"}])):
        resp = await client.get("/api/arenas/com-event-ativo")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {m["event_slug"] for m in data} == {"canal3expo", "retroexpo-2026"}


@pytest.mark.asyncio
async def test_nao_exige_autenticacao(client):
    """Rota pública — sem Depends(require_admin), sem header de auth."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.listar_com_event_ativo", AsyncMock(return_value=[])):
        resp = await client.get("/api/arenas/com-event-ativo")

    assert resp.status_code == 200
