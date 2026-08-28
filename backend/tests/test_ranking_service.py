"""
Testes de services/ranking.py — resolução dos 5 modos de
docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1 (resolver_event_ids).
"""
import pytest
import services.ranking as ranking_svc


def _event(modo_ranking, event_id="ev1", arena_id="m1"):
    return {"id": event_id, "arena_id": arena_id, "modo_ranking": modo_ranking}


# ── zerado ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_zerado_retorna_so_o_proprio_event(fake_pool):
    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("zerado"))

    assert resultado == ["ev1"]
    fake_pool.fetch.assert_not_called()
    fake_pool.fetchrow.assert_not_called()


# ── geral ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_geral_retorna_none(fake_pool):
    """None sinaliza 'sem filtro de event' — placar da plataforma
    inteira, sem opt-out (decisão #8)."""
    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("geral"))

    assert resultado is None
    fake_pool.fetch.assert_not_called()
    fake_pool.fetchrow.assert_not_called()


# ── ultimo_evento ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_ultimo_evento_retorna_event_anterior_mais_recente(fake_pool):
    fake_pool.set_fetchrow({"id": "ev-anterior"})

    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("ultimo_evento"))

    assert resultado == ["ev-anterior"]
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "arena_id = $1 AND id != $2" in sql
    assert "ORDER BY data_inicio DESC" in sql
    assert fake_pool.fetchrow.call_args[0][1:] == ("m1", "ev1")


@pytest.mark.asyncio
async def test_modo_ultimo_evento_sem_outro_event_cai_pro_proprio(fake_pool):
    """Marca só tem esse evento ainda — nenhum 'anterior' pra referenciar."""
    fake_pool.set_fetchrow(None)

    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("ultimo_evento"))

    assert resultado == ["ev1"]


# ── arena ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_arena_agrega_events_nao_zerados_da_arena(fake_pool):
    fake_pool.set_fetch([{"id": "ev1"}, {"id": "ev2"}, {"id": "ev3"}])

    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("marca"))

    assert resultado == ["ev1", "ev2", "ev3"]
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "arena_id = $1 AND modo_ranking != 'zerado'" in sql
    assert fake_pool.fetch.call_args[0][1] == "m1"


@pytest.mark.asyncio
async def test_modo_arena_sem_nenhum_event_participante_cai_pro_proprio(fake_pool):
    """Se nem o próprio event aparecer na query (ex.: corrida entre
    escrever modo_ranking e o commit ficar visível), não pode devolver
    lista vazia — cai pro comportamento mais conservador."""
    fake_pool.set_fetch([])

    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("marca"))

    assert resultado == ["ev1"]


# ── marca_parceiras ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_marca_parceiras_inclui_events_de_arenas_parceiras(fake_pool):
    fake_pool.set_fetch([{"id": "ev1"}, {"id": "ev-parceira"}])

    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("marca_parceiras"))

    assert resultado == ["ev1", "ev-parceira"]
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "arena_origem_id FROM arena_partnerships" in sql
    assert "arena_destino_id = $1 AND ativo = true" in sql
    assert fake_pool.fetch.call_args[0][1] == "m1"


@pytest.mark.asyncio
async def test_modo_marca_parceiras_sem_resultado_cai_pro_proprio(fake_pool):
    fake_pool.set_fetch([])

    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("marca_parceiras"))

    assert resultado == ["ev1"]


# ── modo desconhecido ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_desconhecido_cai_pro_proprio_event(fake_pool):
    """Defesa em profundidade — o CHECK constraint no banco já impede
    isso de acontecer de verdade, mas o serviço não deve quebrar."""
    resultado = await ranking_svc.resolver_event_ids(fake_pool, _event("modo-que-nao-existe"))

    assert resultado == ["ev1"]
