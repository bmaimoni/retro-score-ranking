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


def _evento(slug="canal3expo", publico=True, ativo=True, modo_ranking="zerado", marca_id=None):
    return {
        "id": make_uuid(), "nome": "Canal3 Expo", "slug": slug,
        "ativo": ativo, "publico": publico,
        "logo_url": None, "cor_primaria": None,
        "modo_ranking": modo_ranking, "marca_id": marca_id or make_uuid(),
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


# ── /evento-envio-atual (docs/BACKLOG_2026.md §3 item 3.3) ─────

@pytest.mark.asyncio
async def test_evento_envio_atual_modo_zerado_retorna_o_proprio_slug(client):
    """Zerado não precisa consultar a marca — o próprio evento já é a
    resposta certa, sem query extra."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    evento = _evento(modo_ranking="zerado")

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=evento)), \
         patch("repositories.evento.buscar_evento_envio_atual_da_marca", AsyncMock()) as resolver_mock:
        resp = await client.get("/api/e/canal3expo/evento-envio-atual")

    assert resp.status_code == 200
    assert resp.json()["slug"] == "canal3expo"
    resolver_mock.assert_not_called()


@pytest.mark.asyncio
async def test_evento_envio_atual_modo_agregado_resolve_evento_da_marca(client):
    marca_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    evento = _evento(modo_ranking="marca", marca_id=marca_id)

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=evento)), \
         patch("repositories.evento.buscar_evento_envio_atual_da_marca",
               AsyncMock(return_value={"slug": "evento-mais-recente"})) as resolver_mock:
        resp = await client.get("/api/e/canal3expo/evento-envio-atual")

    assert resp.status_code == 200
    assert resp.json()["slug"] == "evento-mais-recente"
    resolver_mock.assert_called_once_with(pool, marca_id)


@pytest.mark.asyncio
async def test_evento_envio_atual_modo_agregado_sem_candidato_cai_pro_proprio(client):
    """Defesa: se por algum motivo a marca não tiver nenhum evento
    ativo/público (nem o próprio, o que não deveria acontecer), não
    quebra — cai pro slug da própria página."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    evento = _evento(modo_ranking="geral")

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=evento)), \
         patch("repositories.evento.buscar_evento_envio_atual_da_marca", AsyncMock(return_value=None)):
        resp = await client.get("/api/e/canal3expo/evento-envio-atual")

    assert resp.status_code == 200
    assert resp.json()["slug"] == "canal3expo"


@pytest.mark.asyncio
async def test_evento_envio_atual_evento_nao_publico_retorna_403(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=_evento(publico=False))):
        resp = await client.get("/api/e/canal3expo/evento-envio-atual")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_evento_envio_atual_evento_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.get("/api/e/naoexiste/evento-envio-atual")

    assert resp.status_code == 404


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

    with patch("repositories.evento.buscar_por_slug",           AsyncMock(return_value=evento)), \
         patch("repositories.jogo.buscar_por_slug",              AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.listar_ranking_por_eventos", AsyncMock(return_value=entradas)) as listar_mock:
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 200
    data = resp.json()
    assert data["evento"] == "canal3expo"
    assert data["modo_ranking"] == "zerado"
    assert len(data["entradas"]) == 1
    assert data["entradas"][0]["nick"] == "P1"
    # modo 'zerado' resolve pro próprio evento, nenhum outro
    listar_mock.assert_called_once_with(pool, jogo["id"], [evento["id"]])


@pytest.mark.asyncio
async def test_ranking_modo_geral_ignora_filtro_de_evento(client):
    """modo_ranking='geral' (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1.E)
    cai pro placar da plataforma inteira — sem filtro de evento nenhum,
    reaproveitando repositories.entrada.listar_ranking (mesma função do
    placar público sem evento)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    evento = _evento(modo_ranking="geral")
    jogo   = _jogo()
    entradas = [{"id": make_uuid(), "nick": "P1", "pontuacao": 999}]

    with patch("repositories.evento.buscar_por_slug",  AsyncMock(return_value=evento)), \
         patch("repositories.jogo.buscar_por_slug",     AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.listar_ranking",   AsyncMock(return_value=entradas)) as listar_mock, \
         patch("repositories.entrada.listar_ranking_por_eventos", AsyncMock()) as listar_eventos_mock:
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 200
    assert resp.json()["modo_ranking"] == "geral"
    listar_mock.assert_called_once_with(pool, jogo["id"])
    listar_eventos_mock.assert_not_called()


@pytest.mark.asyncio
async def test_ranking_modo_marca_agrega_eventos_da_marca(client):
    """modo_ranking='marca' agrega todos os eventos não-zerados da
    marca (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1.C) — via
    services.ranking.resolver_evento_ids, que consulta a tabela
    eventos direto (não mockada aqui: exercita o serviço real)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_id = make_uuid()
    evento = _evento(modo_ranking="marca", marca_id=marca_id)
    jogo   = _jogo()
    outro_evento_id = make_uuid()
    pool.fetch = AsyncMock(return_value=[{"id": evento["id"]}, {"id": outro_evento_id}])

    with patch("repositories.evento.buscar_por_slug", AsyncMock(return_value=evento)), \
         patch("repositories.jogo.buscar_por_slug",    AsyncMock(return_value=jogo)), \
         patch("repositories.entrada.listar_ranking_por_eventos", AsyncMock(return_value=[])) as listar_mock:
        resp = await client.get("/api/e/canal3expo/ranking/megamania")

    assert resp.status_code == 200
    evento_ids_chamados = listar_mock.call_args[0][2]
    assert set(evento_ids_chamados) == {evento["id"], outro_evento_id}


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
