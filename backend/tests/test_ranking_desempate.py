"""
Testes de regressão: desempate de pontuações iguais no ranking.

Bug original: as queries de ranking ordenavam só por `pontuacao DESC`,
sem critério de desempate. O Postgres não garante ordem estável entre
linhas empatadas — a ordem podia mudar entre consultas (inclusive entre
o snapshot inicial e o refetch disparado por um event SSE), fazendo uma
entry "sumir" de listas truncadas no top N (ex.: top 10 do telão)
sempre que o empate caía bem na fronteira do corte.

Correção: toda ORDER BY de ranking agora inclui `criado_em ASC, id ASC`
(ou `e.criado_em ASC, e.id ASC` nas queries com DISTINCT ON) como
desempate estável e determinístico.

Estes testes travam a presença desse desempate nas queries, para que
ninguém remova acidentalmente no futuro.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import repositories.entry as entry_repo
from main import app
from utils.db import get_pool


def make_uuid():
    return str(uuid.uuid4())


def _normalizar_sql(sql: str) -> str:
    """Colapsa espaços/quebras de linha para facilitar comparação por substring."""
    return " ".join(sql.split())


# ── Nível repositório: garante que a SQL enviada ao driver tem o desempate ────

@pytest.mark.asyncio
async def test_listar_ranking_desempata_por_criado_em_e_id(fake_pool):
    game_id = make_uuid()
    fake_pool.set_fetch([])

    await entry_repo.listar_ranking(fake_pool, game_id)

    sql_chamada = _normalizar_sql(fake_pool.fetch.call_args[0][0])
    assert "ORDER BY pontuacao DESC, criado_em ASC, id ASC" in sql_chamada


@pytest.mark.asyncio
async def test_listar_ranking_por_event_desempata_por_criado_em_e_id(fake_pool):
    game_id   = make_uuid()
    event_id = make_uuid()
    fake_pool.set_fetch([])

    await entry_repo.listar_ranking_por_event(fake_pool, game_id, event_id)

    sql_chamada = _normalizar_sql(fake_pool.fetch.call_args[0][0])
    assert "ORDER BY pontuacao DESC, criado_em ASC, id ASC" in sql_chamada


# ── Nível HTTP: /api/ranking/lideres e /api/e/{slug}/ranking/lideres ─────────

@pytest.mark.asyncio
async def test_lideres_desempata_por_criado_em_e_id(client):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    app.dependency_overrides[get_pool] = lambda: pool

    try:
        resp = await client.get("/api/ranking/lideres")
    finally:
        app.dependency_overrides.pop(get_pool, None)

    assert resp.status_code == 200
    sql_chamada = _normalizar_sql(pool.fetch.call_args[0][0])
    assert "ORDER BY e.game_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC" in sql_chamada


@pytest.mark.asyncio
async def test_lideres_event_desempata_por_criado_em_e_id(client):
    event = {
        "id": make_uuid(), "slug": "canal3expo", "nome": "Canal3 Expo",
        "ativo": True, "publico": True,
        "modo_ranking": "zerado", "arena_id": make_uuid(),
    }
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    app.dependency_overrides[get_pool] = lambda: pool

    try:
        with patch("repositories.event.buscar_por_slug", AsyncMock(return_value=event)):
            resp = await client.get("/api/e/canal3expo/ranking/lideres")
    finally:
        app.dependency_overrides.pop(get_pool, None)

    assert resp.status_code == 200
    sql_chamada = _normalizar_sql(pool.fetch.call_args[0][0])
    assert "ORDER BY e.game_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC" in sql_chamada


# ── Nível comportamental: empate não derruba ninguém do topo N ───────────────

@pytest.mark.asyncio
async def test_ranking_com_empate_no_limite_do_top_n_preserva_ambas_entries(client):
    """
    Reprodução do bug relatado: duas pessoas diferentes empatam em pontuação
    exatamente na fronteira do corte (ex.: top 10 do telão). Antes da
    correção, a ordem entre as duas era indefinida e uma delas podia não
    aparecer dependendo de como o Postgres devolvia o empate. Agora a
    query já entrega ordem determinística, então o endpoint deve sempre
    devolver as duas, na mesma ordem (por criado_em).
    """
    game = {"id": make_uuid(), "slug": "pac-man", "nome": "Pac-Man",
            "score_max": None, "ativo": True}

    entry_mais_antiga = {
        "id": make_uuid(), "nick": "ALICE", "nome": None,
        "pontuacao": 50000, "foto_url": None, "event_id": None,
        "criado_em": "2024-01-01T10:00:00",
    }
    entry_mais_recente = {
        "id": make_uuid(), "nick": "BOB", "nome": None,
        "pontuacao": 50000, "foto_url": None, "event_id": None,
        "criado_em": "2024-01-01T10:05:00",
    }
    # A DB já devolve na ordem correta (criado_em ASC) — é isso que a
    # query real agora garante; aqui simulamos esse retorno determinístico.
    entries_ordenadas = [entry_mais_antiga, entry_mais_recente]

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    try:
        with patch("repositories.game.buscar_por_slug", AsyncMock(return_value=game)), \
             patch("repositories.entry.listar_ranking", AsyncMock(return_value=entries_ordenadas)):
            resp = await client.get("/api/ranking/pac-man")
    finally:
        app.dependency_overrides.pop(get_pool, None)

    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 2
    nicks = [e["nick"] for e in entries]
    assert "ALICE" in nicks and "BOB" in nicks
    # Quem alcançou o score primeiro deve vir antes em caso de empate.
    assert nicks == ["ALICE", "BOB"]
