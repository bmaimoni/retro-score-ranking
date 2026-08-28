"""
Testes de repositories/arena.py — foco na query de resolução de
herança (event → arena → default), que é o coração do
docs/MARCAS_SPEC.md.
"""
import pytest
import repositories.arena as arena_repo


@pytest.mark.asyncio
async def test_resolver_identidade_visual_faz_left_join_com_arenas(fake_pool):
    """
    Confirma que a resolução acontece numa única query (LEFT JOIN),
    não duas idas separadas ao banco — decisão explícita do
    MARCAS_SPEC.md §3 (normalizar em tabela própria não compensava
    exatamente por essa razão).
    """
    fake_pool.set_fetchrow({
        "slug": "canal3expo", "nome": "Canal3 Expo",
        "cor_primaria": "#5e2b82", "tipografia": "arcade",
        "logo_url": "https://cdn/event-logo.png",
    })

    resultado = await arena_repo.resolver_identidade_visual(fake_pool, "canal3expo")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "LEFT JOIN arenas m ON m.id = e.arena_id" in sql
    assert "COALESCE(e.cor_primaria, m.cor_primaria)" in sql
    assert "COALESCE(e.tipografia,   m.tipografia)" in sql or \
           "COALESCE(e.tipografia, m.tipografia)" in sql
    assert resultado["cor_primaria"] == "#5e2b82"


@pytest.mark.asyncio
async def test_resolver_identidade_visual_event_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await arena_repo.resolver_identidade_visual(fake_pool, "nao-existe")
    assert resultado is None


@pytest.mark.asyncio
async def test_criar_arena_repository(fake_pool):
    fake_pool.set_fetchrow({
        "id": "abc", "nome": "Canal3", "slug": "canal3",
        "cor_primaria": "#5e2b82", "tipografia": "arcade",
        "logo_url": None, "criado_em": "2026-01-01",
    })

    resultado = await arena_repo.criar(fake_pool, "Canal3", "canal3", "#5e2b82", "arcade", None)

    assert resultado["slug"] == "canal3"
    # Confirma ordem/quantidade dos parâmetros passados pro INSERT
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("Canal3", "canal3", "#5e2b82", "arcade", None)


@pytest.mark.asyncio
async def test_atualizar_arena_campos_parciais(fake_pool):
    """Só os campos presentes em `dados` devem ser repassados como
    não-None — os demais ficam None pro COALESCE preservar o valor atual."""
    fake_pool.set_fetchrow({
        "id": "abc", "nome": "Canal3", "slug": "canal3",
        "cor_primaria": "#ff0000", "tipografia": "arcade",
        "logo_url": None, "criado_em": "2026-01-01",
    })

    await arena_repo.atualizar(fake_pool, "abc", {"cor_primaria": "#ff0000"})

    args = fake_pool.fetchrow.call_args[0]
    # (sql, arena_id, nome, cor_primaria, tipografia, logo_url)
    assert args[1] == "abc"
    assert args[2] is None          # nome não foi passado
    assert args[3] == "#ff0000"     # cor_primaria foi passado
    assert args[4] is None          # tipografia não foi passado


@pytest.mark.asyncio
async def test_atualizar_arena_itens_por_pagina(fake_pool):
    """BACKLOG_2026.md §3 item 3.2 — config única por arena, todo
    event dela herda, sem exceção por event."""
    fake_pool.set_fetchrow({
        "id": "abc", "nome": "Canal3", "slug": "canal3",
        "cor_primaria": None, "tipografia": None, "logo_url": None,
        "itens_por_pagina": 50, "criado_em": "2026-01-01",
    })

    resultado = await arena_repo.atualizar(fake_pool, "abc", {"itens_por_pagina": 50})

    assert resultado["itens_por_pagina"] == 50
    args = fake_pool.fetchrow.call_args[0]
    assert args[-1] == 50


# ── buscar_owner_user_id: trava de revogação do titular (decisão #10) ───────────

@pytest.mark.asyncio
async def test_buscar_owner_user_id_retorna_titular(fake_pool):
    dono_id = "550e8400-e29b-41d4-a716-446655440000"
    fake_pool.set_fetchrow({"owner_user_id": dono_id})

    resultado = await arena_repo.buscar_owner_user_id(fake_pool, "arena-1")

    assert resultado == dono_id


@pytest.mark.asyncio
async def test_buscar_owner_user_id_arena_sem_titular_retorna_none(fake_pool):
    """owner_user_id nasce NULL em toda arena existente após a
    migration 019 — precisa ser atribuído manualmente depois."""
    fake_pool.set_fetchrow({"owner_user_id": None})

    resultado = await arena_repo.buscar_owner_user_id(fake_pool, "arena-1")

    assert resultado is None


@pytest.mark.asyncio
async def test_buscar_owner_user_id_arena_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)

    resultado = await arena_repo.buscar_owner_user_id(fake_pool, "nao-existe")

    assert resultado is None


# ── transferir_titularidade (decisão #11) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_transferir_titularidade_atualiza_dono(fake_pool):
    novo_dono_id = "novo-dono"
    fake_pool.set_fetchrow({
        "id": "arena-1", "nome": "Canal3", "slug": "canal3",
        "cor_primaria": "#5e2b82", "tipografia": "arcade", "logo_url": None,
        "owner_user_id": novo_dono_id, "criado_em": "2026-01-01",
    })

    resultado = await arena_repo.transferir_titularidade(fake_pool, "arena-1", novo_dono_id)

    assert resultado["owner_user_id"] == novo_dono_id
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "UPDATE arenas SET owner_user_id" in sql
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("arena-1", novo_dono_id)


@pytest.mark.asyncio
async def test_transferir_titularidade_arena_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await arena_repo.transferir_titularidade(fake_pool, "nao-existe", "u1")
    assert resultado is None


# ── listar_onde_e_dono: trava de exclusão de conta (EXCLUSAO_CONTA_SPEC.md #5) ─

# ── listar_com_event_ativo (BACKLOG_2026.md §2 item 2.1) ───────────────────────

@pytest.mark.asyncio
async def test_listar_com_event_ativo_filtra_ativo_e_publico(fake_pool):
    fake_pool.set_fetch([{"id": "m1", "nome": "Canal3", "slug": "canal3", "logo_url": None}])

    resultado = await arena_repo.listar_com_event_ativo(fake_pool)

    assert len(resultado) == 1
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "JOIN events e ON e.arena_id = m.id" in sql
    assert "WHERE e.ativo = true AND e.publico = true" in sql
    assert "DISTINCT m.id" in sql


@pytest.mark.asyncio
async def test_listar_com_event_ativo_vazio(fake_pool):
    fake_pool.set_fetch([])
    resultado = await arena_repo.listar_com_event_ativo(fake_pool)
    assert resultado == []


@pytest.mark.asyncio
async def test_listar_onde_e_dono_retorna_arenas(fake_pool):
    fake_pool.set_fetch([{"id": "m1", "nome": "Canal3"}])

    resultado = await arena_repo.listar_onde_e_dono(fake_pool, "u1")

    assert resultado == [{"id": "m1", "nome": "Canal3"}]
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "owner_user_id = $1" in sql


@pytest.mark.asyncio
async def test_listar_onde_e_dono_vazio_quando_nao_e_dono_de_nada(fake_pool):
    fake_pool.set_fetch([])
    resultado = await arena_repo.listar_onde_e_dono(fake_pool, "u1")
    assert resultado == []
