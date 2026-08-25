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
async def test_listar_feed_admin_expoe_pendente_motivo_sempre(fake_pool):
    """Sem isso o painel admin não consegue distinguir 'rate_limit' de
    'identificacao_ambigua' (decisão #7 do NICKNAME_SPEC.md) — coluna
    simples, sempre selecionada, não só quando status='pendentes'
    (pendente=true também aparece misturado em 'todos').

    Achado (Fase 5 -> feed admin): a migração de listar_pendentes/
    contar_pendentes (endpoint dedicado, removido) pro feed unificado
    esqueceu de levar e.pendente_motivo junto, deixando o painel sem
    conseguir mostrar o motivo real da pendência."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.pendente_motivo" in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_expoe_user_id(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.user_id" in sql


# ── Contexto de ranking só em status='pendentes' (ex-listar_pendentes) ─────────

@pytest.mark.asyncio
async def test_listar_feed_admin_status_pendentes_traz_contexto_de_ranking(fake_pool):
    """melhor_score_atual/lider_pontuacao/posicao_se_aprovado — o
    painel usa isso pra mostrar "ficaria em Nº lugar" na fila de
    moderação (frontend/admin.html:cardEntrada). Achado (Fase 5): a
    migração pro feed unificado nunca levou essas 3 subqueries junto,
    deixando esse bloco da UI sempre invisível desde então."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, status="pendentes")

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "AS melhor_score_atual" in sql
    assert "AS lider_pontuacao" in sql
    assert "AS posicao_se_aprovado" in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_status_todos_nao_paga_custo_do_contexto(fake_pool):
    """Fora da fila de pendentes essas 3 subqueries correlacionadas não
    servem pra nada (frontend só lê quando e.pendente é true) — não
    faz sentido pagar o custo em toda página do feed."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, status="todos")

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "melhor_score_atual" not in sql
    assert "lider_pontuacao" not in sql
    assert "posicao_se_aprovado" not in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_status_pendentes_exclui_arquivado(fake_pool):
    """Achado (Fase 5): sem essa exclusão, uma entrada
    identificacao_ambigua já auto-arquivada (30 dias expirados)
    continuava aparecendo pra sempre como 'aguardando decisão' — o
    antigo listar_pendentes excluía arquivado=true, o filtro novo do
    feed não excluía."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, status="pendentes")

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.pendente = true AND e.arquivado = false" in sql


# ── lazy-archive embutido no feed admin (decisão #8 do NICKNAME_SPEC.md) ───────
# Achado (Fase 5): o gatilho só existia dentro de listar_pendentes/
# contar_pendentes — como nada mais chamava essas funções depois da
# migração pro feed unificado, o arquivamento automático de 30 dias
# parou de disparar de verdade. Movido pra dentro de
# listar_feed_admin/contar_feed_admin, que são as funções realmente
# chamadas a cada carregamento do painel agora.

@pytest.mark.asyncio
async def test_listar_feed_admin_arquiva_identificacao_ambigua_expirada_antes_de_listar(fake_pool):
    """Sem job agendado (NICKNAME_SPEC.md §4) — a checagem de 30 dias
    roda embutida toda vez que o feed é consultado."""
    fake_pool.set_fetch([])

    await entrada_repo.listar_feed_admin(fake_pool)

    # execute (o UPDATE de arquivamento) roda antes do fetch (SELECT)
    assert fake_pool.execute.called
    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    assert "pendente_motivo = 'identificacao_ambigua'" in sql
    assert "30 days" in sql
    assert "arquivado = true" in sql


@pytest.mark.asyncio
async def test_contar_feed_admin_tambem_arquiva_antes_de_contar(fake_pool):
    """X-Total-Count precisa refletir o mesmo estado pós-arquivamento
    que a listagem — senão o header e as linhas retornadas divergem."""
    fake_pool.set_fetchval(0)

    await entrada_repo.contar_feed_admin(fake_pool)

    assert fake_pool.execute.called


@pytest.mark.asyncio
async def test_arquivamento_nao_toca_rate_limit(fake_pool):
    """rate_limit não tem prazo — só identificacao_ambigua é elegível
    ao arquivamento automático."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool)

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



# ── listar_feed_admin / contar_feed_admin — filtros (BACKLOG_2026.md §4) ────────

@pytest.mark.asyncio
async def test_listar_feed_admin_sem_filtros_so_evento_ids(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, limit=50, offset=0, evento_ids=None)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "WHERE ($3::uuid[] IS NULL OR e.evento_id = ANY($3::uuid[]))" in sql
    assert "JOIN eventos ev ON ev.id = e.evento_id" in sql
    args = fake_pool.fetch.call_args[0]
    assert args[1:] == (50, 0, None)


@pytest.mark.asyncio
async def test_listar_feed_admin_status_visiveis(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, status="visiveis")
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.pendente = false AND e.no_ranking = true" in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_status_ocultos(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, status="ocultos")
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.pendente = false AND e.no_ranking = false" in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_status_pendentes(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, status="pendentes")
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.pendente = true" in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_status_todos_sem_filtro_extra(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, status="todos")
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.pendente = false" not in sql
    assert "e.pendente = true" not in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_filtro_data(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, data_de="2026-01-01", data_ate="2026-01-31")
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.criado_em::date >= $4" in sql
    assert "e.criado_em::date <= $5" in sql
    args = fake_pool.fetch.call_args[0]
    assert args[4] == "2026-01-01"
    assert args[5] == "2026-01-31"


@pytest.mark.asyncio
async def test_listar_feed_admin_filtro_jogo_id(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, jogo_id="j1")
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.jogo_id = $4" in sql
    assert fake_pool.fetch.call_args[0][4] == "j1"


@pytest.mark.asyncio
async def test_listar_feed_admin_filtro_sem_foto(fake_pool):
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, sem_foto=True)
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.foto_url IS NULL" in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_filtro_sem_identificacao(fake_pool):
    """user_id IS NULL AND nome IS NULL — mesmo critério de
    marcar_pendente_identificacao_ambigua (NICKNAME_SPEC.md decisão #7).
    Filtro separado de sem_foto (decisão do item 4.1: dois filtros,
    não um só)."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, sem_identificacao=True)
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.user_id IS NULL AND e.nome IS NULL" in sql
    assert "e.foto_url IS NULL" not in sql


@pytest.mark.asyncio
async def test_listar_feed_admin_busca_pesquisa_nick_jogo_evento(fake_pool):
    """Sem full-text search — ILIKE direto sobre os 3 campos já
    existentes no feed (decisão do item 4.4)."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(fake_pool, busca="novato")
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.nick ILIKE $4" in sql
    assert "j.nome ILIKE $4" in sql
    assert "ev.nome ILIKE $4" in sql
    assert fake_pool.fetch.call_args[0][4] == "%novato%"


@pytest.mark.asyncio
async def test_listar_feed_admin_filtros_combinados_indices_sequenciais(fake_pool):
    """Vários filtros juntos — os índices posicionais não podem colidir
    nem pular (senão o parâmetro errado vai pro placeholder errado)."""
    fake_pool.set_fetch([])
    await entrada_repo.listar_feed_admin(
        fake_pool, data_de="2026-01-01", jogo_id="j1", busca="novato",
    )
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "e.criado_em::date >= $4" in sql
    assert "e.jogo_id = $5" in sql
    assert "e.nick ILIKE $6" in sql
    args = fake_pool.fetch.call_args[0]
    assert args[4] == "2026-01-01"
    assert args[5] == "j1"
    assert args[6] == "%novato%"


@pytest.mark.asyncio
async def test_contar_feed_admin_aplica_mesmos_filtros_que_listar(fake_pool):
    """contar_feed_admin não tem limit/offset — os índices dos filtros
    começam em $1, não $3. Precisa aplicar exatamente os mesmos filtros
    de listar_feed_admin, senão X-Total-Count diverge da página."""
    fake_pool.set_fetchval(0)
    await entrada_repo.contar_feed_admin(fake_pool, status="pendentes", jogo_id="j1", busca="x")

    sql = " ".join(fake_pool.fetchval.call_args[0][0].split())
    assert "e.pendente = true" in sql
    assert "e.jogo_id = $2" in sql
    assert "e.nick ILIKE $3" in sql
    assert "JOIN eventos ev ON ev.id = e.evento_id" in sql
    args = fake_pool.fetchval.call_args[0]
    assert args[1:] == (None, "j1", "%x%")


@pytest.mark.asyncio
async def test_listar_lideres_por_eventos_none_e_modo_geral_sem_filtro(fake_pool):
    """evento_ids=None (modo 'geral') não filtra por evento nenhum —
    a query decide isso via ($2::uuid[] IS NULL OR ...)."""
    fake_pool.set_fetch([])

    await entrada_repo.listar_lideres_por_eventos(fake_pool, "ev-atual", None)

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "$2::uuid[] IS NULL" in sql
    assert fake_pool.fetch.call_args[0][1:] == ("ev-atual", None)
