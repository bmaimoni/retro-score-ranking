"""
Testes de repositories/admin_vinculo.py — CRUD e a função de checagem
de acesso, que é o coração da autorização escopada.

Ver docs/MARCAS_SPEC.md §6.
"""
import uuid
import pytest
import repositories.admin_vinculo as admin_vinculo_repo


def make_uuid():
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_listar_por_usuario_filtra_por_ativo(fake_pool):
    """Só vínculos ativos — inativos não devem contar pra autorização."""
    fake_pool.set_fetch([
        {"id": make_uuid(), "user_id": "u1", "escopo": "super",
         "marca_id": None, "evento_id": None, "ativo": True, "criado_em": "2026-01-01"},
    ])

    resultado = await admin_vinculo_repo.listar_por_usuario(fake_pool, "u1")

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "ativo = true" in sql
    assert len(resultado) == 1


@pytest.mark.asyncio
async def test_criar_vinculo_super(fake_pool):
    fake_pool.set_fetchrow({
        "id": make_uuid(), "user_id": "u1", "escopo": "super",
        "marca_id": None, "evento_id": None, "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await admin_vinculo_repo.criar(fake_pool, "u1", "super")

    assert resultado["escopo"] == "super"
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("u1", "super", None, None)


@pytest.mark.asyncio
async def test_criar_vinculo_e_idempotente_via_on_conflict(fake_pool):
    """A query usa ON CONFLICT ... DO UPDATE SET ativo=true — reativa em
    vez de duplicar (mesmo padrão de evento_jogos/placar_eventos)."""
    fake_pool.set_fetchrow({
        "id": make_uuid(), "user_id": "u1", "escopo": "evento",
        "marca_id": None, "evento_id": "ev1", "ativo": True, "criado_em": "2026-01-01",
    })

    await admin_vinculo_repo.criar(fake_pool, "u1", "evento", evento_id="ev1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET ativo = true" in sql


@pytest.mark.asyncio
async def test_atualizar_ativo_desativa_sem_delete(fake_pool):
    fake_pool.set_fetchrow({
        "id": "v1", "user_id": "u1", "escopo": "evento",
        "marca_id": None, "evento_id": "ev1", "ativo": False, "criado_em": "2026-01-01",
    })

    resultado = await admin_vinculo_repo.atualizar_ativo(fake_pool, "v1", False)

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "UPDATE admin_vinculos SET ativo" in sql
    assert "DELETE" not in sql
    assert resultado["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_ativo_vinculo_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await admin_vinculo_repo.atualizar_ativo(fake_pool, "nao-existe", False)
    assert resultado is None


# ── tem_acesso_evento: a query central de autorização ──────────────────────────

@pytest.mark.asyncio
async def test_tem_acesso_evento_cobre_os_3_escopos_na_mesma_query(fake_pool):
    """
    Confirma que a query cobre super OR marca-bate OR evento-bate numa
    query só, sem N+1 (uma checagem por request administrativo, não uma
    por vínculo do usuário).
    """
    fake_pool.set_fetchrow({"?column?": 1})

    resultado = await admin_vinculo_repo.tem_acesso_evento(fake_pool, "u1", "ev1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "escopo = 'super'" in sql
    assert "escopo = 'marca'" in sql
    assert "escopo = 'evento'" in sql
    assert "av.ativo   = true" in sql or "av.ativo = true" in sql
    assert resultado is True


@pytest.mark.asyncio
async def test_tem_acesso_evento_sem_vinculo_retorna_false(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await admin_vinculo_repo.tem_acesso_evento(fake_pool, "u1", "ev1")
    assert resultado is False


@pytest.mark.asyncio
async def test_listar_eventos_acessiveis(fake_pool):
    id1, id2 = make_uuid(), make_uuid()
    fake_pool.set_fetch([{"id": id1}, {"id": id2}])

    resultado = await admin_vinculo_repo.listar_eventos_acessiveis(fake_pool, "u1")

    assert resultado == [id1, id2]
    assert all(isinstance(x, str) for x in resultado)
