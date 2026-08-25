"""
Testes de services/ranking.py — resolução dos 5 modos de
docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1 (resolver_evento_ids).
"""
import pytest
import services.ranking as ranking_svc


def _evento(modo_ranking, evento_id="ev1", marca_id="m1"):
    return {"id": evento_id, "marca_id": marca_id, "modo_ranking": modo_ranking}


# ── zerado ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_zerado_retorna_so_o_proprio_evento(fake_pool):
    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("zerado"))

    assert resultado == ["ev1"]
    fake_pool.fetch.assert_not_called()
    fake_pool.fetchrow.assert_not_called()


# ── geral ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_geral_retorna_none(fake_pool):
    """None sinaliza 'sem filtro de evento' — placar da plataforma
    inteira, sem opt-out (decisão #8)."""
    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("geral"))

    assert resultado is None
    fake_pool.fetch.assert_not_called()
    fake_pool.fetchrow.assert_not_called()


# ── ultimo_evento ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_ultimo_evento_retorna_evento_anterior_mais_recente(fake_pool):
    fake_pool.set_fetchrow({"id": "ev-anterior"})

    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("ultimo_evento"))

    assert resultado == ["ev-anterior"]
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "marca_id = $1 AND id != $2" in sql
    assert "ORDER BY data_inicio DESC" in sql
    assert fake_pool.fetchrow.call_args[0][1:] == ("m1", "ev1")


@pytest.mark.asyncio
async def test_modo_ultimo_evento_sem_outro_evento_cai_pro_proprio(fake_pool):
    """Marca só tem esse evento ainda — nenhum 'anterior' pra referenciar."""
    fake_pool.set_fetchrow(None)

    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("ultimo_evento"))

    assert resultado == ["ev1"]


# ── marca ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_marca_agrega_eventos_nao_zerados_da_marca(fake_pool):
    fake_pool.set_fetch([{"id": "ev1"}, {"id": "ev2"}, {"id": "ev3"}])

    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("marca"))

    assert resultado == ["ev1", "ev2", "ev3"]
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "marca_id = $1 AND modo_ranking != 'zerado'" in sql
    assert fake_pool.fetch.call_args[0][1] == "m1"


@pytest.mark.asyncio
async def test_modo_marca_sem_nenhum_evento_participante_cai_pro_proprio(fake_pool):
    """Se nem o próprio evento aparecer na query (ex.: corrida entre
    escrever modo_ranking e o commit ficar visível), não pode devolver
    lista vazia — cai pro comportamento mais conservador."""
    fake_pool.set_fetch([])

    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("marca"))

    assert resultado == ["ev1"]


# ── marca_parceiras ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_marca_parceiras_inclui_eventos_de_marcas_parceiras(fake_pool):
    fake_pool.set_fetch([{"id": "ev1"}, {"id": "ev-parceira"}])

    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("marca_parceiras"))

    assert resultado == ["ev1", "ev-parceira"]
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "marca_origem_id FROM marcas_parcerias" in sql
    assert "marca_destino_id = $1 AND ativo = true" in sql
    assert fake_pool.fetch.call_args[0][1] == "m1"


@pytest.mark.asyncio
async def test_modo_marca_parceiras_sem_resultado_cai_pro_proprio(fake_pool):
    fake_pool.set_fetch([])

    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("marca_parceiras"))

    assert resultado == ["ev1"]


# ── modo desconhecido ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modo_desconhecido_cai_pro_proprio_evento(fake_pool):
    """Defesa em profundidade — o CHECK constraint no banco já impede
    isso de acontecer de verdade, mas o serviço não deve quebrar."""
    resultado = await ranking_svc.resolver_evento_ids(fake_pool, _evento("modo-que-nao-existe"))

    assert resultado == ["ev1"]
