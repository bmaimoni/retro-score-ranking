"""
Testes do router público de marcas — GET /api/marcas/com-evento-ativo.
Ver docs/BACKLOG_2026.md §2 item 2.1: tela inicial sem ?evento= na URL
(sem fallback hardcoded desde a Fase 6) precisa descobrir pra qual
marca/evento mandar o visitante.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


def _marca(**overrides):
    base = {"id": make_uuid(), "nome": "Canal3", "slug": "canal3", "logo_url": None}
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


@pytest.mark.asyncio
async def test_lista_marcas_com_evento_slug_resolvido(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca = _marca()

    with patch("repositories.marca.listar_com_evento_ativo", AsyncMock(return_value=[marca])), \
         patch("repositories.evento.buscar_evento_envio_atual_da_marca",
               AsyncMock(return_value={"slug": "canal3expo-2026"})):
        resp = await client.get("/api/marcas/com-evento-ativo")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["evento_slug"] == "canal3expo-2026"
    assert data[0]["nome"] == "Canal3"


@pytest.mark.asyncio
async def test_lista_vazia_quando_nenhuma_marca_qualifica(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.listar_com_evento_ativo", AsyncMock(return_value=[])):
        resp = await client.get("/api/marcas/com-evento-ativo")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_marca_sem_evento_resolvivel_fica_de_fora_sem_quebrar(client):
    """Defesa: se por algum motivo o resolver não achar evento pra uma
    marca que passou no filtro da listagem (corrida entre as duas
    queries), a resposta não quebra — só omite essa marca."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_ok = _marca(nome="Canal3")
    marca_sem_evento = _marca(nome="RetroExpo")

    with patch("repositories.marca.listar_com_evento_ativo",
               AsyncMock(return_value=[marca_ok, marca_sem_evento])), \
         patch("repositories.evento.buscar_evento_envio_atual_da_marca",
               AsyncMock(side_effect=[{"slug": "canal3expo"}, None])):
        resp = await client.get("/api/marcas/com-evento-ativo")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["nome"] == "Canal3"


@pytest.mark.asyncio
async def test_multiplas_marcas_retorna_todas_resolvidas(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_a = _marca(nome="Canal3")
    marca_b = _marca(nome="RetroExpo")

    with patch("repositories.marca.listar_com_evento_ativo",
               AsyncMock(return_value=[marca_a, marca_b])), \
         patch("repositories.evento.buscar_evento_envio_atual_da_marca",
               AsyncMock(side_effect=[{"slug": "canal3expo"}, {"slug": "retroexpo-2026"}])):
        resp = await client.get("/api/marcas/com-evento-ativo")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {m["evento_slug"] for m in data} == {"canal3expo", "retroexpo-2026"}


@pytest.mark.asyncio
async def test_nao_exige_autenticacao(client):
    """Rota pública — sem Depends(require_admin), sem header de auth."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.listar_com_evento_ativo", AsyncMock(return_value=[])):
        resp = await client.get("/api/marcas/com-evento-ativo")

    assert resp.status_code == 200
