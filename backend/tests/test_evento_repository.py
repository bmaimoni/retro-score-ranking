"""
Testes de repositories/evento.py — foco em
buscar_evento_envio_atual_da_marca (docs/BACKLOG_2026.md §3 item 3.3):
resolve pra qual evento o QR/link de envio deve apontar quando a
página em exibição está em ranking agregado.
"""
import pytest
import repositories.evento as evento_repo


@pytest.mark.asyncio
async def test_buscar_evento_envio_atual_filtra_ativo_e_publico(fake_pool):
    fake_pool.set_fetchrow({
        "id": "e1", "nome": "Canal3 Expo", "slug": "canal3expo",
        "ativo": True, "publico": True, "logo_url": None, "cor_primaria": None,
        "tipografia": None, "marca_id": "m1", "modo_ranking": "marca",
        "data_inicio": "2026-01-01", "data_fim": "2026-02-01", "criado_em": "2026-01-01",
    })

    resultado = await evento_repo.buscar_evento_envio_atual_da_marca(fake_pool, "m1")

    assert resultado["slug"] == "canal3expo"
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "WHERE marca_id = $1 AND ativo = true AND publico = true" in sql
    assert fake_pool.fetchrow.call_args[0][1] == "m1"


@pytest.mark.asyncio
async def test_buscar_evento_envio_atual_prioriza_janela_aberta_depois_mais_recente(fake_pool):
    """Ordem: evento com janela aberta agora vem primeiro; entre os
    que empatam nisso, o de data_inicio mais recente."""
    fake_pool.set_fetch([])
    await evento_repo.buscar_evento_envio_atual_da_marca(fake_pool, "m1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "ORDER BY (data_inicio <= now() AND data_fim >= now()) DESC, data_inicio DESC" in sql
    assert "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_buscar_evento_envio_atual_marca_sem_evento_participante_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await evento_repo.buscar_evento_envio_atual_da_marca(fake_pool, "m1")
    assert resultado is None
