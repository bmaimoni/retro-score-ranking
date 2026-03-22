"""
Testes de integração do fluxo de moderação.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin

ADMIN_SECRET = "test-secret-mod"
AUTH = {"Authorization": f"Bearer {ADMIN_SECRET}"}


def make_uuid():
    return str(uuid.uuid4())


def make_entrada(nick="PLAYER1", pontuacao=50000, jogo_id=None,
                 no_ranking=True, pendente=False,
                 foto_url="https://cdn.example.com/foto.jpg"):
    return {
        "id": make_uuid(), "jogo_id": jogo_id or make_uuid(),
        "nick": nick, "nick_norm": nick.lower().strip(),
        "pontuacao": pontuacao, "foto_url": foto_url,
        "no_ranking": no_ranking, "superado": False, "pendente": pendente,
        "ip_hash": "abc123", "criado_em": "2024-01-01T00:00:00Z",
        "moderado_em": None, "moderado_por": None,
    }


def _pool_com_slug(slug="pac-man"):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"slug": slug})
    return pool


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[require_admin] = lambda: ADMIN_SECRET
    yield
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(autouse=True)
def clear_pool_override():
    yield
    app.dependency_overrides.pop(get_pool, None)


@pytest.mark.asyncio
async def test_ocultar_remove_do_ranking_e_emite_sse(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, no_ranking=True)
    entrada_ocultada = {**entrada, "no_ranking": False}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entrada.atualizar_visibilidade",
               AsyncMock(return_value=entrada_ocultada)), \
         patch("routers.admin.broker.publish", broker_mock):
        resp = await client.patch(
            f"/api/admin/entradas/{entrada['id']}",
            json={"no_ranking": False}, headers=AUTH)

    assert resp.status_code == 200
    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "ocultar"


@pytest.mark.asyncio
async def test_reativar_volta_ao_ranking_e_emite_sse(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, no_ranking=False)
    entrada_reativada = {**entrada, "no_ranking": True}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug("galaga")

    with patch("repositories.entrada.atualizar_visibilidade",
               AsyncMock(return_value=entrada_reativada)), \
         patch("routers.admin.broker.publish", broker_mock):
        resp = await client.patch(
            f"/api/admin/entradas/{entrada['id']}",
            json={"no_ranking": True}, headers=AUTH)

    assert resp.status_code == 200
    assert broker_mock.call_args[0][1] == "reativar"
    payload = broker_mock.call_args[0][2]
    assert "entrada" in payload


@pytest.mark.asyncio
async def test_aprovar_pendente_entra_no_ranking_com_sse(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, pendente=True, no_ranking=False)
    entrada_aprovada = {**entrada, "pendente": False, "no_ranking": True}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entrada.resolver_pendente",
               AsyncMock(return_value=entrada_aprovada)), \
         patch("routers.admin.broker.publish", broker_mock):
        resp = await client.patch(
            f"/api/admin/entradas/{entrada['id']}/pendente",
            json={"aprovar": True}, headers=AUTH)

    assert resp.status_code == 200
    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "novo_registro"


@pytest.mark.asyncio
async def test_rejeitar_pendente_nao_entra_no_ranking(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, pendente=True, no_ranking=False)
    entrada_rejeitada = {**entrada, "pendente": False, "no_ranking": False}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entrada.resolver_pendente",
               AsyncMock(return_value=entrada_rejeitada)), \
         patch("routers.admin.broker.publish", broker_mock):
        resp = await client.patch(
            f"/api/admin/entradas/{entrada['id']}/pendente",
            json={"aprovar": False}, headers=AUTH)

    assert resp.status_code == 200
    broker_mock.assert_not_called()


@pytest.mark.asyncio
async def test_ranking_exclui_entradas_ocultas(client):
    jogo = {"id": make_uuid(), "nome": "Pac-Man", "slug": "pac-man",
            "score_max": None, "ativo": True}
    entradas_visiveis = [
        {"id": make_uuid(), "nick": "P1", "pontuacao": 9000,
         "foto_url": None, "criado_em": "2024-01-01"},
    ]

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.jogo.buscar_por_slug", AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.listar_ranking",
               AsyncMock(return_value=entradas_visiveis)):
        resp = await client.get("/api/ranking/pac-man")

    assert resp.status_code == 200
    assert len(resp.json()["entradas"]) == 1