"""
Testes dos endpoints públicos de event:
  GET /api/e/{slug}/config
  GET /api/e/{slug}/games
  GET /api/e/{slug}/ranking/{game_slug}
  GET /api/e/{slug}/ranking/lideres  (nota: rota mais específica vem antes)
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


def _event(slug="canal3expo", publico=True, ativo=True, modo_ranking="zerado", arena_id=None):
    return {
        "id": make_uuid(), "nome": "Canal3 Expo", "slug": slug,
        "ativo": ativo, "publico": publico,
        "logo_url": None, "cor_primaria": None,
        "modo_ranking": modo_ranking, "arena_id": arena_id or make_uuid(),
    }


def _game():
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
async def test_config_event_retorna_dados_publicos(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    identidade = {**_event(), "tipografia": None}

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=_event())), \
         patch("repositories.arena.resolver_identidade_visual", AsyncMock(return_value=identidade)):
        resp = await client.get("/api/e/canal3expo/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "canal3expo"
    assert "nome" in data
    assert "logo_url" in data
    assert "cor_primaria" in data
    assert "tipografia" in data


@pytest.mark.asyncio
async def test_config_event_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.get("/api/e/naoexiste/config")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_config_event_inativo_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_slug",
               AsyncMock(return_value=_event(ativo=False))):
        resp = await client.get("/api/e/canal3expo/config")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_config_event_nao_publico_retorna_403(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_slug",
               AsyncMock(return_value=_event(publico=False))):
        resp = await client.get("/api/e/canal3expo/config")

    assert resp.status_code == 403


# ── /event-envio-atual (docs/BACKLOG_2026.md §3 item 3.3) ─────

@pytest.mark.asyncio
async def test_event_envio_atual_modo_zerado_retorna_o_proprio_slug(client):
    """Zerado não precisa consultar a arena — o próprio event já é a
    resposta certa, sem query extra."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    event = _event(modo_ranking="zerado")

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=event)), \
         patch("repositories.event.buscar_event_envio_atual_da_arena", AsyncMock()) as resolver_mock:
        resp = await client.get("/api/e/canal3expo/event-envio-atual")

    assert resp.status_code == 200
    assert resp.json()["slug"] == "canal3expo"
    resolver_mock.assert_not_called()


@pytest.mark.asyncio
async def test_event_envio_atual_modo_agregado_resolve_event_da_arena(client):
    arena_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    event = _event(modo_ranking="marca", arena_id=arena_id)

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=event)), \
         patch("repositories.event.buscar_event_envio_atual_da_arena",
               AsyncMock(return_value={"slug": "event-mais-recente"})) as resolver_mock:
        resp = await client.get("/api/e/canal3expo/event-envio-atual")

    assert resp.status_code == 200
    assert resp.json()["slug"] == "event-mais-recente"
    resolver_mock.assert_called_once_with(pool, arena_id)


@pytest.mark.asyncio
async def test_event_envio_atual_modo_agregado_sem_candidato_cai_pro_proprio(client):
    """Defesa: se por algum motivo a arena não tiver nenhum event
    ativo/público (nem o próprio, o que não deveria acontecer), não
    quebra — cai pro slug da própria página."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    event = _event(modo_ranking="geral")

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=event)), \
         patch("repositories.event.buscar_event_envio_atual_da_arena", AsyncMock(return_value=None)):
        resp = await client.get("/api/e/canal3expo/event-envio-atual")

    assert resp.status_code == 200
    assert resp.json()["slug"] == "canal3expo"


@pytest.mark.asyncio
async def test_event_envio_atual_event_nao_publico_retorna_403(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=_event(publico=False))):
        resp = await client.get("/api/e/canal3expo/event-envio-atual")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_event_envio_atual_event_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.get("/api/e/naoexiste/event-envio-atual")

    assert resp.status_code == 404


# ── /games ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_games_do_event_retorna_lista(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    games = [{"id": make_uuid(), "nome": "Megamania", "slug": "megamania",
               "score_max": None, "ativo": True, "ordem": 0}]

    with patch("repositories.event.buscar_por_slug",    AsyncMock(return_value=_event())), \
         patch("repositories.event_game.listar_por_event", AsyncMock(return_value=games)):
        resp = await client.get("/api/e/canal3expo/games")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["slug"] == "megamania"


@pytest.mark.asyncio
async def test_games_event_nao_publico_retorna_403(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_slug",
               AsyncMock(return_value=_event(publico=False))):
        resp = await client.get("/api/e/canal3expo/games")

    assert resp.status_code == 403


# ── /ranking/{game_slug} ──────────────────────────────────────

@pytest.mark.asyncio
async def test_ranking_filtrado_por_event(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    event = _event()
    game   = _game()
    entries = [
        {"id": make_uuid(), "nick": "P1", "nome": "João Silva",
         "pontuacao": 50000, "foto_url": None,
         "event_id": event["id"], "criado_em": "2024-01-01"},
    ]

    with patch("repositories.event.buscar_por_slug",           AsyncMock(return_value=event)), \
         patch("repositories.game.buscar_por_slug",              AsyncMock(return_value=game)), \
         patch("repositories.entry.listar_ranking_por_events", AsyncMock(return_value=entries)) as listar_mock:
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 200
    data = resp.json()
    assert data["event"] == "canal3expo"
    assert data["modo_ranking"] == "zerado"
    assert len(data["entries"]) == 1
    assert data["entries"][0]["nick"] == "P1"
    # modo 'zerado' resolve pro próprio event, nenhum outro
    listar_mock.assert_called_once_with(pool, game["id"], [event["id"]])


@pytest.mark.asyncio
async def test_ranking_modo_geral_ignora_filtro_de_event(client):
    """modo_ranking='geral' (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1.E)
    cai pro placar da plataforma inteira — sem filtro de event nenhum,
    reaproveitando repositories.entry.listar_ranking (mesma função do
    placar público sem event)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    event = _event(modo_ranking="geral")
    game   = _game()
    entries = [{"id": make_uuid(), "nick": "P1", "pontuacao": 999}]

    with patch("repositories.event.buscar_por_slug",  AsyncMock(return_value=event)), \
         patch("repositories.game.buscar_por_slug",     AsyncMock(return_value=game)), \
         patch("repositories.entry.listar_ranking",   AsyncMock(return_value=entries)) as listar_mock, \
         patch("repositories.entry.listar_ranking_por_events", AsyncMock()) as listar_events_mock:
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 200
    assert resp.json()["modo_ranking"] == "geral"
    listar_mock.assert_called_once_with(pool, game["id"])
    listar_events_mock.assert_not_called()


@pytest.mark.asyncio
async def test_ranking_modo_arena_agrega_events_da_arena(client):
    """modo_ranking='marca' agrega todos os events não-zerados da
    arena (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1.C) — via
    services.ranking.resolver_event_ids, que consulta a tabela
    events direto (não mockada aqui: exercita o serviço real)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_id = make_uuid()
    event = _event(modo_ranking="marca", arena_id=arena_id)
    game   = _game()
    outro_event_id = make_uuid()
    pool.fetch = AsyncMock(return_value=[{"id": event["id"]}, {"id": outro_event_id}])

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=event)), \
         patch("repositories.game.buscar_por_slug",    AsyncMock(return_value=game)), \
         patch("repositories.entry.listar_ranking_por_events", AsyncMock(return_value=[])) as listar_mock:
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 200
    event_ids_chamados = listar_mock.call_args[0][2]
    assert set(event_ids_chamados) == {event["id"], outro_event_id}


@pytest.mark.asyncio
async def test_ranking_game_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=_event())), \
         patch("repositories.game.buscar_por_slug",    AsyncMock(return_value=None)):
        resp = await client.get("/api/e/canal3expo/ranking/naoexiste")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ranking_event_nao_publico_retorna_403(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_slug",
               AsyncMock(return_value=_event(publico=False))):
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 403
