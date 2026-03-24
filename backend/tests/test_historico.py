"""
Testes do endpoint GET /api/ranking/{slug}/historico/{nick}.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


def _entrada(pontuacao: int, superado=False, pendente=False, criado_em="2024-01-01T10:00:00"):
    return {
        "id": make_uuid(),
        "nick": "PLAYER1",
        "nome": "Fulano Silva",
        "pontuacao": pontuacao,
        "foto_url": None,
        "no_ranking": not superado and not pendente,
        "superado": superado,
        "pendente": pendente,
        "arquivado": False,
        "criado_em": criado_em,
    }


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


@pytest.mark.asyncio
async def test_historico_retorna_entradas_do_nick(client):
    """Endpoint retorna histórico ordenado do mais recente para o mais antigo."""
    jogo = {"id": make_uuid(), "nome": "Megamania", "slug": "megamania",
            "score_max": None, "ativo": True}
    historico = [
        _entrada(15000, criado_em="2024-01-03T10:00:00"),
        _entrada(12000, superado=True, criado_em="2024-01-02T10:00:00"),
        _entrada(8000,  superado=True, criado_em="2024-01-01T10:00:00"),
    ]

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.jogo.buscar_por_slug",      AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.historico_nick",     AsyncMock(return_value=historico)), \
         patch("services.nick.normalizar_nick",           return_value="player1"):
        resp = await client.get("/api/ranking/megamania/historico/PLAYER1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["nick"] == "PLAYER1"
    assert data["jogo_slug"] == "megamania"
    assert len(data["historico"]) == 3
    assert data["historico"][0]["pontuacao"] == 15000


@pytest.mark.asyncio
async def test_historico_jogo_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.jogo.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.get("/api/ranking/naoexiste/historico/PLAYER1")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_historico_nick_sem_entradas_retorna_lista_vazia(client):
    jogo = {"id": make_uuid(), "nome": "Megamania", "slug": "megamania",
            "score_max": None, "ativo": True}

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.jogo.buscar_por_slug",  AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.historico_nick", AsyncMock(return_value=[])), \
         patch("services.nick.normalizar_nick",       return_value="desconhecido"):
        resp = await client.get("/api/ranking/megamania/historico/DESCONHECIDO")

    assert resp.status_code == 200
    assert resp.json()["historico"] == []


@pytest.mark.asyncio
async def test_historico_inclui_entradas_superadas_e_pendentes(client):
    """Histórico deve incluir todos os tipos de entrada, não só as ativas."""
    jogo = {"id": make_uuid(), "nome": "Megamania", "slug": "megamania",
            "score_max": None, "ativo": True}
    historico = [
        _entrada(20000),
        _entrada(15000, superado=True),
        _entrada(5000,  pendente=True),
    ]

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.jogo.buscar_por_slug",  AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.historico_nick", AsyncMock(return_value=historico)), \
         patch("services.nick.normalizar_nick",       return_value="player1"):
        resp = await client.get("/api/ranking/megamania/historico/PLAYER1")

    entradas = resp.json()["historico"]
    assert len(entradas) == 3
    assert any(e["superado"] for e in entradas)
    assert any(e["pendente"] for e in entradas)


@pytest.mark.asyncio
async def test_historico_usa_nick_normalizado(client):
    """O endpoint normaliza o nick antes de buscar no banco."""
    jogo = {"id": make_uuid(), "nome": "Megamania", "slug": "megamania",
            "score_max": None, "ativo": True}

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    historico_mock = AsyncMock(return_value=[])
    normalizar_mock = MagicMock(return_value="player_1")

    with patch("repositories.jogo.buscar_por_slug",  AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.historico_nick", historico_mock), \
         patch("services.nick.normalizar_nick",       normalizar_mock):
        await client.get("/api/ranking/megamania/historico/PLAYER 1")

    normalizar_mock.assert_called_once_with("PLAYER 1")
    historico_mock.assert_called_once()
    _, nick_arg = historico_mock.call_args[0][1], historico_mock.call_args[0][2]
    assert nick_arg == "player_1"
