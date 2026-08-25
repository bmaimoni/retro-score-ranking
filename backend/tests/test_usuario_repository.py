"""
Testes de repositories/usuario.py — leitura/edição de perfil.
Ver docs/BACKLOG_2026.md §1 e migration 020.
"""
import pytest
import repositories.usuario as usuario_repo


@pytest.mark.asyncio
async def test_buscar_perfil(fake_pool):
    fake_pool.set_fetchrow({
        "id": "u1", "email": "p@x.com", "nome": "Pessoa", "foto_url": None,
        "status": "ativo", "nome_completo": "Pessoa Completa",
        "data_nascimento": None, "cidade": None, "estado": None, "telefone": None,
        "avatar_id": None, "criado_em": "2026-01-01", "ultimo_login_em": None,
    })

    resultado = await usuario_repo.buscar_perfil(fake_pool, "u1")

    assert resultado["nome_completo"] == "Pessoa Completa"


@pytest.mark.asyncio
async def test_buscar_perfil_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await usuario_repo.buscar_perfil(fake_pool, "nao-existe")
    assert resultado is None


@pytest.mark.asyncio
async def test_atualizar_perfil_campos_parciais(fake_pool):
    """Só os campos presentes em `dados` devem ser repassados como
    não-None — os demais ficam None pro COALESCE preservar o valor atual."""
    fake_pool.set_fetchrow({
        "id": "u1", "email": "p@x.com", "nome": "Pessoa", "foto_url": None,
        "status": "ativo", "nome_completo": None, "data_nascimento": None,
        "cidade": "São Paulo", "estado": None, "telefone": None,
        "avatar_id": None, "criado_em": "2026-01-01", "ultimo_login_em": None,
    })

    await usuario_repo.atualizar_perfil(fake_pool, "u1", {"cidade": "São Paulo"})

    args = fake_pool.fetchrow.call_args[0]
    # (sql, user_id, nome_completo, data_nascimento, cidade, estado, telefone, avatar_id)
    assert args[1] == "u1"
    assert args[2] is None            # nome_completo não foi passado
    assert args[4] == "São Paulo"     # cidade foi passado
    assert args[5] is None            # estado não foi passado


@pytest.mark.asyncio
async def test_atualizar_perfil_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await usuario_repo.atualizar_perfil(fake_pool, "nao-existe", {"cidade": "X"})
    assert resultado is None


# ── Exclusão de conta (docs/EXCLUSAO_CONTA_SPEC.md) ─────────────────────────────

@pytest.mark.asyncio
async def test_solicitar_exclusao_seta_timestamp(fake_pool):
    fake_pool.set_fetchrow({"id": "u1", "exclusao_solicitada_em": "2026-01-01T00:00:00"})

    resultado = await usuario_repo.solicitar_exclusao(fake_pool, "u1")

    assert resultado["exclusao_solicitada_em"] is not None
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "exclusao_solicitada_em = now()" in sql
    assert "exclusao_solicitada_em IS NULL" in sql  # idempotente: não reinicia prazo


@pytest.mark.asyncio
async def test_solicitar_exclusao_ja_pendente_retorna_none(fake_pool):
    """WHERE exclusao_solicitada_em IS NULL não bate — já tinha uma
    solicitação em andamento, não reinicia o prazo."""
    fake_pool.set_fetchrow(None)
    resultado = await usuario_repo.solicitar_exclusao(fake_pool, "u1")
    assert resultado is None


@pytest.mark.asyncio
async def test_cancelar_exclusao_limpa_timestamp(fake_pool):
    fake_pool.set_fetchrow({"id": "u1", "exclusao_solicitada_em": None})

    resultado = await usuario_repo.cancelar_exclusao(fake_pool, "u1")

    assert resultado["exclusao_solicitada_em"] is None
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "exclusao_solicitada_em = NULL" in sql


@pytest.mark.asyncio
async def test_cancelar_exclusao_sem_solicitacao_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await usuario_repo.cancelar_exclusao(fake_pool, "u1")
    assert resultado is None


@pytest.mark.asyncio
async def test_buscar_para_exclusao(fake_pool):
    fake_pool.set_fetchrow({"id": "u1", "email": "p@x.com", "status": "ativo", "exclusao_solicitada_em": None})
    resultado = await usuario_repo.buscar_para_exclusao(fake_pool, "u1")
    assert resultado["status"] == "ativo"


@pytest.mark.asyncio
async def test_listar_exclusoes_pendentes_ordenado_mais_antigo_primeiro(fake_pool):
    fake_pool.set_fetch([
        {"id": "u1", "email": "a@x.com", "nome": "A", "exclusao_solicitada_em": "2026-01-01", "elegivel": True},
        {"id": "u2", "email": "b@x.com", "nome": "B", "exclusao_solicitada_em": "2026-02-01", "elegivel": False},
    ])

    resultado = await usuario_repo.listar_exclusoes_pendentes(fake_pool)

    assert len(resultado) == 2
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "ORDER BY exclusao_solicitada_em ASC" in sql
    assert "30 days" in sql


@pytest.mark.asyncio
async def test_anonimizar_limpa_users_identities_e_magic_link(fake_pool):
    fake_pool.set_fetchrow({"id": "u1", "status": "excluido"})

    resultado = await usuario_repo.anonimizar(fake_pool, "u1", "pessoa@example.com")

    assert resultado["status"] == "excluido"
    # magic_link_tokens e identities via execute(); users via fetchrow()
    execute_sqls = [" ".join(c.args[0].split()) for c in fake_pool.execute.call_args_list]
    assert any("magic_link_tokens" in s and "anonimizado@anonimizado.invalid" in s for s in execute_sqls)
    assert any("identities" in s and "anonimizado.invalid" in s for s in execute_sqls)
    users_sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "status = 'excluido'" in users_sql
    assert "email = NULL" in users_sql


@pytest.mark.asyncio
async def test_anonimizar_sem_email_nao_toca_magic_link_tokens(fake_pool):
    """Usuário que nunca teve e-mail preenchido (login só Google sem
    e-mail verificado, caso raro) — nada a limpar em magic_link_tokens."""
    fake_pool.set_fetchrow({"id": "u1", "status": "excluido"})

    await usuario_repo.anonimizar(fake_pool, "u1", None)

    execute_sqls = [" ".join(c.args[0].split()) for c in fake_pool.execute.call_args_list]
    assert not any("magic_link_tokens" in s for s in execute_sqls)


@pytest.mark.asyncio
async def test_desativar_pontuacoes_conta_linhas_afetadas(fake_pool):
    fake_pool.execute.return_value = "UPDATE 4"

    resultado = await usuario_repo.desativar_pontuacoes(fake_pool, "u1", "pessoa@x.com")

    assert resultado == 4
    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    assert "arquivado = true" in sql
    assert "user_id = $1" in sql
