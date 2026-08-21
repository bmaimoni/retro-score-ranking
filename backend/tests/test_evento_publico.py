"""
Testes dos endpoints públicos de evento:
  GET /api/e/{slug}/config
  GET /api/e/{slug}/jogos
  GET /api/e/{slug}/ranking/{jogo_slug}
  GET /api/e/{slug}/ranking/lideres  (nota: rota mais específica vem antes)
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


def _evento(slug="canal3expo", publico=True, ativo=True):
    return {
        "id": make_uuid(), "nome": "Canal3 Expo", "slug": slug,
        "ativo": ativo, "publico": publico,
        "logo_url": None, "cor_primaria": None,
    }


def _jogo():
    return {
        "id": make_uuid(), "nome": "Megamania", "slug": "megamania",
        "score_max": None, "ativo": True,
    }


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


# ── /config ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_evento_retorna_dados_publicos(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    identidade = {**_evento(), "tipografia": None}

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=_evento())), \
         patch("repositories.marca.resolver_identidade_visual", AsyncMock(return_value=identidade)):
        resp = await client.get("/api/e/canal3expo/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "canal3expo"
    assert "nome" in data
    assert "logo_url" in data
    assert "cor_primaria" in data
    assert "tipografia" in data


@pytest.mark.asyncio
async def test_config_evento_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.get("/api/e/naoexiste/config")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_config_evento_inativo_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_slug",
               AsyncMock(return_value=_evento(ativo=False))):
        resp = await client.get("/api/e/canal3expo/config")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_config_evento_nao_publico_retorna_403(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_slug",
               AsyncMock(return_value=_evento(publico=False))):
        resp = await client.get("/api/e/canal3expo/config")

    assert resp.status_code == 403


# ── /jogos ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_jogos_do_evento_retorna_lista(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    jogos = [{"id": make_uuid(), "nome": "Megamania", "slug": "megamania",
               "score_max": None, "ativo": True, "ordem": 0}]

    with patch("repositories.evento.buscar_por_slug",    AsyncMock(return_value=_evento())), \
         patch("repositories.evento_jogo.listar_por_evento", AsyncMock(return_value=jogos)):
        resp = await client.get("/api/e/canal3expo/jogos")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["slug"] == "megamania"


@pytest.mark.asyncio
async def test_jogos_evento_nao_publico_retorna_403(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_slug",
               AsyncMock(return_value=_evento(publico=False))):
        resp = await client.get("/api/e/canal3expo/jogos")

    assert resp.status_code == 403


# ── /ranking/{jogo_slug} ──────────────────────────────────────

@pytest.mark.asyncio
async def test_ranking_filtrado_por_evento(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    evento = _evento()
    jogo   = _jogo()
    entradas = [
        {"id": make_uuid(), "nick": "P1", "nome": "João Silva",
         "pontuacao": 50000, "foto_url": None,
         "evento_id": evento["id"], "criado_em": "2024-01-01"},
    ]

    with patch("repositories.evento.buscar_por_slug",          AsyncMock(return_value=evento)), \
         patch("repositories.jogo.buscar_por_slug",             AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.listar_ranking_por_evento", AsyncMock(return_value=entradas)):
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 200
    data = resp.json()
    assert data["evento"] == "canal3expo"
    assert len(data["entradas"]) == 1
    assert data["entradas"][0]["nick"] == "P1"


@pytest.mark.asyncio
async def test_ranking_jogo_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=_evento())), \
         patch("repositories.jogo.buscar_por_slug",    AsyncMock(return_value=None)):
        resp = await client.get("/api/e/canal3expo/ranking/naoexiste")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ranking_evento_nao_publico_retorna_403(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_slug",
               AsyncMock(return_value=_evento(publico=False))):
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 403
