"""
Testes de repositories/entrada.py — funções novas de
docs/NICKNAME_SPEC.md (decisões #7, #8, #11).
"""
import pytest
import repositories.entrada as entrada_repo


# ── vincular_retroativamente (decisão #11) ──────────────────────────────────

@pytest.mark.asyncio
async def test_vincular_retroativamente_conta_linhas_afetadas(fake_pool):
    fake_pool.execute.return_value = "UPDATE 3"

    resultado = await entrada_repo.vincular_retroativamente(fake_pool, "novato", "u1")

    assert resultado == 3
    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    assert "SET user_id = $2" in sql
    assert "user_id IS NULL" in sql


@pytest.mark.asyncio
async def test_vincular_retroativamente_zero_entradas_orfas(fake_pool):
    fake_pool.execute.return_value = "UPDATE 0"
    resultado = await entrada_repo.vincular_retroativamente(fake_pool, "novato", "u1")
    assert resultado == 0


# ── marcar_pendente_identificacao_ambigua (decisão #7) ──────────────────────

@pytest.mark.asyncio
async def test_marcar_pendente_identificacao_ambigua(fake_pool):
    fake_pool.execute.return_value = "UPDATE 2"

    resultado = await entrada_repo.marcar_pendente_identificacao_ambigua(fake_pool, "veterano")

    assert resultado == 2
    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    assert "pendente_motivo = 'identificacao_ambigua'" in sql
    assert "user_id IS NULL" in sql
    assert "nome IS NULL" in sql
    assert "arquivado = false" in sql


# ── lazy-archive embutido em listar_pendentes/contar_pendentes (decisão #8) ─

@pytest.mark.asyncio
async def test_listar_pendentes_arquiva_identificacao_ambigua_expirada_antes_de_listar(fake_pool):
    """Sem job agendado (NICKNAME_SPEC.md §4) — a checagem de 30 dias
    roda embutida toda vez que a fila é consultada."""
    fake_pool.set_fetch([])

    await entrada_repo.listar_pendentes(fake_pool)

    # execute (o UPDATE de arquivamento) roda antes do fetch (SELECT)
    assert fake_pool.execute.called
    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    assert "pendente_motivo = 'identificacao_ambigua'" in sql
    assert "30 days" in sql
    assert "arquivado = true" in sql


@pytest.mark.asyncio
async def test_contar_pendentes_tambem_arquiva_antes_de_contar(fake_pool):
    """X-Total-Count precisa refletir o mesmo estado pós-arquivamento
    que a listagem — senão o header e as linhas retornadas divergem."""
    fake_pool.set_fetchval(0)

    await entrada_repo.contar_pendentes(fake_pool)

    assert fake_pool.execute.called


@pytest.mark.asyncio
async def test_arquivamento_nao_toca_rate_limit(fake_pool):
    """rate_limit não tem prazo — só identificacao_ambigua é elegível
    ao arquivamento automático."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_pendentes(fake_pool)

    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    assert "rate_limit" not in sql
