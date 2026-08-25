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


@pytest.mark.asyncio
async def test_listar_pendentes_expoe_pendente_motivo(fake_pool):
    """Sem isso o painel admin não consegue distinguir 'rate_limit' de
    'identificacao_ambigua' (decisão #7 do NICKNAME_SPEC.md)."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_pendentes(fake_pool)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.pendente_motivo" in sql


@pytest.mark.asyncio
async def test_listar_pendentes_expoe_user_id(fake_pool):
    """Painel de moderação precisa do user_id pra oferecer 'ver
    histórico de nicks' (decisão #4 do NICKNAME_SPEC.md)."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_pendentes(fake_pool)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.user_id" in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_expoe_user_id(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.user_id" in sql


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


# ── listar_por_usuario (BACKLOG_2026.md item 1.4) ───────────────────────────────

@pytest.mark.asyncio
async def test_listar_por_usuario_junta_jogo_evento_marca(fake_pool):
    fake_pool.set_fetch([{
        "id": "e1", "nick": "Campeao", "pontuacao": 5000, "foto_url": None,
        "no_ranking": True, "superado": False, "pendente": False, "arquivado": False,
        "criado_em": "2026-01-01",
        "jogo_id": "j1", "jogo_nome": "Pac-Man", "jogo_slug": "pac-man",
        "evento_id": "ev1", "evento_nome": "Canal3 Expo", "evento_slug": "canal3expo",
        "marca_id": "m1", "marca_nome": "Canal3",
    }])

    resultado = await entrada_repo.listar_por_usuario(fake_pool, "u1")

    assert len(resultado) == 1
    assert resultado[0]["marca_nome"] == "Canal3"
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "JOIN eventos ev" in sql
    assert "JOIN marcas m" in sql
    assert "e.user_id = $1" in sql


@pytest.mark.asyncio
async def test_listar_por_usuario_sem_pontuacoes_retorna_vazio(fake_pool):
    fake_pool.set_fetch([])
    resultado = await entrada_repo.listar_por_usuario(fake_pool, "u1")
    assert resultado == []


# ── listar_ranking_por_eventos / listar_lideres_por_eventos ────────────────────
# Ranking agregado — docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1, modos
# 'ultimo_evento'/'marca'/'marca_parceiras'.

@pytest.mark.asyncio
async def test_listar_ranking_por_eventos_filtra_por_lista_e_expoe_origem(fake_pool):
    fake_pool.set_fetch([{
        "id": "e1", "nick": "Campeao", "nome": None, "pontuacao": 5000,
        "foto_url": None, "evento_id": "ev1", "user_id": None, "criado_em": "2026-01-01",
        "evento_nome": "Canal3 Expo", "evento_slug": "canal3expo", "marca_nome": "Canal3",
    }])

    resultado = await entrada_repo.listar_ranking_por_eventos(fake_pool, "j1", ["ev1", "ev2"])

    assert len(resultado) == 1
    assert resultado[0]["marca_nome"] == "Canal3"
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.evento_id = ANY($2::uuid[])" in sql
    assert "JOIN eventos ev ON ev.id = e.evento_id" in sql
    assert "JOIN marcas m ON m.id = ev.marca_id" in sql
    assert "ORDER BY e.pontuacao DESC, e.criado_em ASC, e.id ASC" in sql
    assert fake_pool.fetch.call_args[0][1:] == ("j1", ["ev1", "ev2"])


@pytest.mark.asyncio
async def test_listar_ranking_por_eventos_vazio(fake_pool):
    fake_pool.set_fetch([])
    resultado = await entrada_repo.listar_ranking_por_eventos(fake_pool, "j1", ["ev1"])
    assert resultado == []


@pytest.mark.asyncio
async def test_listar_lideres_por_eventos_agrega_top1_por_jogo(fake_pool):
    fake_pool.set_fetch([
        {"jogo_id": "j1", "slug": "pac-man", "nick": "CAMPEAO", "pontuacao": 99000},
    ])

    resultado = await entrada_repo.listar_lideres_por_eventos(fake_pool, "ev-atual", ["ev1", "ev2"])

    assert resultado["j1"]["nick"] == "CAMPEAO"
    assert fake_pool.fetch.call_args[0][1:] == ("ev-atual", ["ev1", "ev2"])


@pytest.mark.asyncio
async def test_listar_lideres_por_eventos_none_e_modo_geral_sem_filtro(fake_pool):
    """evento_ids=None (modo 'geral') não filtra por evento nenhum —
    a query decide isso via ($2::uuid[] IS NULL OR ...)."""
    fake_pool.set_fetch([])

    await entrada_repo.listar_lideres_por_eventos(fake_pool, "ev-atual", None)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "$2::uuid[] IS NULL" in sql
    assert fake_pool.fetch.call_args[0][1:] == ("ev-atual", None)
