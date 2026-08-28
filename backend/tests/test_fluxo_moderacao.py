"""
Testes de integração do fluxo de moderação.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

ADMIN_SECRET = "test-secret-mod"
AUTH = {"Authorization": f"Bearer {ADMIN_SECRET}"}
ADMIN_CTX = AdminContext(identificador="admin", user_id=None, super=True)


def make_uuid():
    return str(uuid.uuid4())


def make_entry(nick="PLAYER1", pontuacao=50000, game_id=None,
                 no_ranking=True, pendente=False,
                 foto_url="https://cdn.example.com/foto.jpg"):
    return {
        "id": make_uuid(), "game_id": game_id or make_uuid(),
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
    app.dependency_overrides[require_admin] = lambda: ADMIN_CTX
    yield
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(autouse=True)
def clear_pool_override():
    yield
    app.dependency_overrides.pop(get_pool, None)


@pytest.mark.asyncio
async def test_ocultar_remove_do_ranking_e_emite_sse(client):
    game_id = make_uuid()
    entry = make_entry(game_id=game_id, no_ranking=True)
    entry_ocultada = {**entry, "no_ranking": False}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entry.atualizar_visibilidade",
               AsyncMock(return_value=entry_ocultada)), \
         patch("routers.admin.broker.publish", broker_mock):
        resp = await client.patch(
            f"/api/admin/entries/{entry['id']}",
            json={"no_ranking": False}, headers=AUTH)

    assert resp.status_code == 200
    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "ocultar"


@pytest.mark.asyncio
async def test_reativar_volta_ao_ranking_e_emite_sse(client):
    game_id = make_uuid()
    entry = make_entry(game_id=game_id, no_ranking=False)
    entry_reativada = {**entry, "no_ranking": True}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug("galaga")

    with patch("repositories.entry.atualizar_visibilidade",
               AsyncMock(return_value=entry_reativada)), \
         patch("routers.admin.broker.publish", broker_mock):
        resp = await client.patch(
            f"/api/admin/entries/{entry['id']}",
            json={"no_ranking": True}, headers=AUTH)

    assert resp.status_code == 200
    assert broker_mock.call_args[0][1] == "reativar"
    payload = broker_mock.call_args[0][2]
    assert "entry" in payload


@pytest.mark.asyncio
async def test_aprovar_pendente_entra_no_ranking_com_sse(client):
    game_id = make_uuid()
    entry = make_entry(game_id=game_id, pendente=True, no_ranking=False)
    entry_aprovada = {**entry, "pendente": False, "no_ranking": True}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entry.resolver_pendente",
               AsyncMock(return_value=entry_aprovada)), \
         patch("routers.admin.broker.publish", broker_mock):
        resp = await client.patch(
            f"/api/admin/entries/{entry['id']}/pendente",
            json={"aprovar": True}, headers=AUTH)

    assert resp.status_code == 200
    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "novo_registro"


@pytest.mark.asyncio
async def test_rejeitar_pendente_nao_entra_no_ranking(client):
    game_id = make_uuid()
    entry = make_entry(game_id=game_id, pendente=True, no_ranking=False)
    entry_rejeitada = {**entry, "pendente": False, "no_ranking": False}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entry.resolver_pendente",
               AsyncMock(return_value=entry_rejeitada)), \
         patch("routers.admin.broker.publish", broker_mock):
        resp = await client.patch(
            f"/api/admin/entries/{entry['id']}/pendente",
            json={"aprovar": False}, headers=AUTH)

    assert resp.status_code == 200
    broker_mock.assert_not_called()


@pytest.mark.asyncio
async def test_ranking_exclui_entries_ocultas(client):
    game = {"id": make_uuid(), "nome": "Pac-Man", "slug": "pac-man",
            "score_max": None, "ativo": True}
    entries_visiveis = [
        {"id": make_uuid(), "nick": "P1", "pontuacao": 9000,
         "foto_url": None, "criado_em": "2024-01-01"},
    ]

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.game.buscar_por_slug", AsyncMock(return_value=game)), \
         patch("repositories.entry.listar_ranking",
               AsyncMock(return_value=entries_visiveis)):
        resp = await client.get("/api/ranking/pac-man")

    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 1


# ── Arquivamento no ranking ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ranking_exclui_entries_arquivadas(client):
    """Entradas com arquivado=true não devem aparecer no ranking público."""
    game = {"id": make_uuid(), "nome": "Enduro", "slug": "enduro",
            "score_max": None, "ativo": True}
    # Só retorna entries não-arquivadas (repository já filtra)
    entries_visiveis = [
        {"id": make_uuid(), "nick": "ACE", "nome": "Ana Silva",
         "pontuacao": 9000, "foto_url": None, "criado_em": "2024-01-01"},
    ]

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.game.buscar_por_slug",     AsyncMock(return_value=game)), \
         patch("repositories.entry.listar_ranking",    AsyncMock(return_value=entries_visiveis)):
        resp = await client.get("/api/ranking/enduro")

    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 1
    assert resp.json()["entries"][0]["nick"] == "ACE"


@pytest.mark.asyncio
async def test_ranking_retorna_nome_do_jogador(client):
    """Campo nome deve aparecer nas entries do ranking."""
    game = {"id": make_uuid(), "nome": "Enduro", "slug": "enduro",
            "score_max": None, "ativo": True}
    entries = [
        {"id": make_uuid(), "nick": "ACE", "nome": "Ana Silva",
         "pontuacao": 9000, "foto_url": None, "criado_em": "2024-01-01"},
    ]

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.game.buscar_por_slug",  AsyncMock(return_value=game)), \
         patch("repositories.entry.listar_ranking", AsyncMock(return_value=entries)):
        resp = await client.get("/api/ranking/enduro")

    assert resp.status_code == 200
    assert resp.json()["entries"][0]["nome"] == "Ana Silva"