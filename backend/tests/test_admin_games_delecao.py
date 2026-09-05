"""
Testes de DELETE /api/admin/games/{id} — deleção física real, só quando
o game não tem nenhuma entry nem vínculo de event.
Ver docs/SUPER_SPEC.md §7 (Fase 4): entries.game_id é CASCADE — sem essa
guarda, apagar um game com pontuação registrada destruiria recorde real
de jogador.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

SUPER_CTX = AdminContext(identificador="admin", user_id=None, super=True)
NAO_SUPER_CTX = AdminContext(
    identificador="pessoa@x.com", user_id="u1", super=False,
    vinculos=[{"arena_id": "m1", "role": "admin"}],
)


def make_uuid():
    return str(uuid.uuid4())


def make_game(**overrides):
    base = {
        "id": make_uuid(), "slug": "moonwalker-duplicado", "nome": "Moonwalker",
        "ativo": True, "score_max": None, "pendente_aprovacao": False,
        "criado_em": "2026-01-01", "igdb_id": None,
        "plataforma": None, "ano_lancamento": None, "capa_url": None, "gameplay_url": None,
        "generos": None, "geracoes": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_super_apaga_game_sem_uso(client):
    game = make_game()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("repositories.game.contar_uso", AsyncMock(return_value={"entries": 0, "vinculos": 0})), \
         patch("repositories.game.deletar_se_sem_uso", AsyncMock(return_value=True)):
        resp = await client.request("DELETE", f"/api/admin/games/{game['id']}",
            json={"confirmar_slug": game["slug"]})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_apagar_game_com_entries_bloqueado(client):
    """O caso catastrófico que motivou a guarda: entries.game_id é
    CASCADE, então sem essa checagem o DELETE apagaria pontuação real
    de jogador junto."""
    game = make_game()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("repositories.game.contar_uso", AsyncMock(return_value={"entries": 15, "vinculos": 1})):
        resp = await client.request("DELETE", f"/api/admin/games/{game['id']}",
            json={"confirmar_slug": game["slug"]})

    assert resp.status_code == 409
    assert "15 pontua" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_apagar_game_com_vinculo_sem_entries_bloqueado(client):
    game = make_game()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("repositories.game.contar_uso", AsyncMock(return_value={"entries": 0, "vinculos": 2})):
        resp = await client.request("DELETE", f"/api/admin/games/{game['id']}",
            json={"confirmar_slug": game["slug"]})

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_apagar_game_slug_confirmacao_errado(client):
    game = make_game()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)):
        resp = await client.request("DELETE", f"/api/admin/games/{game['id']}",
            json={"confirmar_slug": "nome-errado"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_apagar_game_inexistente_404(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.request("DELETE", f"/api/admin/games/{make_uuid()}",
            json={"confirmar_slug": "qualquer"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nao_super_nao_apaga_game(client):
    app.dependency_overrides[require_admin] = lambda: NAO_SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.request("DELETE", f"/api/admin/games/{make_uuid()}",
        json={"confirmar_slug": "qualquer"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_listar_games_sem_uso_exige_super(client):
    app.dependency_overrides[require_admin] = lambda: NAO_SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get("/api/admin/games/sem-uso")

    assert resp.status_code == 403
