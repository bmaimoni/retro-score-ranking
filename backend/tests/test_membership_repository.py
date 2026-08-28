"""
Testes de repositories/membership.py — CRUD e a função de checagem
de acesso, que é o coração da autorização escopada.

Ver docs/PERMISSOES_SPEC.md (migration 019 — role por arena,
scope='evento' eliminado).
"""
import uuid
import pytest
import repositories.membership as membership_repo


def make_uuid():
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_listar_por_usuario_filtra_por_ativo(fake_pool):
    """Só vínculos ativos — inativos não devem contar pra autorização."""
    fake_pool.set_fetch([
        {"id": make_uuid(), "user_id": "u1", "scope": "super",
         "arena_id": None, "role": None, "ativo": True, "criado_em": "2026-01-01"},
    ])

    resultado = await membership_repo.listar_por_usuario(fake_pool, "u1")

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "ativo = true" in sql
    assert len(resultado) == 1


@pytest.mark.asyncio
async def test_criar_vinculo_super(fake_pool):
    fake_pool.set_fetchrow({
        "id": make_uuid(), "user_id": "u1", "scope": "super",
        "arena_id": None, "role": None, "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await membership_repo.criar(fake_pool, "u1", "super")

    assert resultado["scope"] == "super"
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("u1", "super", None, None)


@pytest.mark.asyncio
async def test_criar_vinculo_arena_com_role(fake_pool):
    fake_pool.set_fetchrow({
        "id": make_uuid(), "user_id": "u1", "scope": "marca",
        "arena_id": "m1", "role": "moderador", "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await membership_repo.criar(fake_pool, "u1", "marca", role="moderador", arena_id="m1")

    assert resultado["role"] == "moderador"
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("u1", "marca", "m1", "moderador")


@pytest.mark.asyncio
async def test_criar_vinculo_e_idempotente_via_on_conflict(fake_pool):
    """A query usa ON CONFLICT ... DO UPDATE SET ativo=true, role=$4 —
    reativa (e atualiza nível) em vez de duplicar."""
    fake_pool.set_fetchrow({
        "id": make_uuid(), "user_id": "u1", "scope": "marca",
        "arena_id": "m1", "role": "admin", "ativo": True, "criado_em": "2026-01-01",
    })

    await membership_repo.criar(fake_pool, "u1", "marca", role="admin", arena_id="m1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET ativo = true, role = $4" in sql


@pytest.mark.asyncio
async def test_atualizar_ativo_desativa_sem_delete(fake_pool):
    fake_pool.set_fetchrow({
        "id": "v1", "user_id": "u1", "scope": "marca",
        "arena_id": "m1", "role": "admin", "ativo": False, "criado_em": "2026-01-01",
    })

    resultado = await membership_repo.atualizar_ativo(fake_pool, "v1", False)

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "UPDATE memberships SET ativo" in sql
    assert "DELETE" not in sql
    assert resultado["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_ativo_vinculo_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await membership_repo.atualizar_ativo(fake_pool, "nao-existe", False)
    assert resultado is None


@pytest.mark.asyncio
async def test_buscar_por_id(fake_pool):
    fake_pool.set_fetchrow({
        "id": "v1", "user_id": "u1", "scope": "marca",
        "arena_id": "m1", "role": "admin", "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await membership_repo.buscar_por_id(fake_pool, "v1")

    assert resultado["role"] == "admin"


@pytest.mark.asyncio
async def test_buscar_por_id_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await membership_repo.buscar_por_id(fake_pool, "nao-existe")
    assert resultado is None


# ── tem_vinculo_admin_ativo: pré-requisito da transferência de titularidade ────

@pytest.mark.asyncio
async def test_tem_vinculo_admin_ativo_true(fake_pool):
    fake_pool.set_fetchrow({"?column?": 1})
    resultado = await membership_repo.tem_vinculo_admin_ativo(fake_pool, "u1", "m1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "role = 'admin'" in sql
    assert "ativo = true" in sql
    assert resultado is True


@pytest.mark.asyncio
async def test_tem_vinculo_admin_ativo_false_quando_so_moderador(fake_pool):
    """A query já filtra role='admin' — um vínculo moderador não conta
    (moderador nunca vira titular sem antes virar admin)."""
    fake_pool.set_fetchrow(None)
    resultado = await membership_repo.tem_vinculo_admin_ativo(fake_pool, "u1", "m1")
    assert resultado is False


# ── tem_acesso_event: a query central de autorização ──────────────────────────

@pytest.mark.asyncio
async def test_tem_acesso_event_cobre_super_e_arena_na_mesma_query(fake_pool):
    """
    Confirma que a query cobre super OR arena-bate numa query só, sem
    N+1. scope='evento' foi eliminado (migration 019) — não deve mais
    aparecer na query.
    """
    fake_pool.set_fetchrow({"?column?": 1})

    resultado = await membership_repo.tem_acesso_event(fake_pool, "u1", "ev1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "scope = 'super'" in sql
    assert "scope = 'marca'" in sql
    assert "scope = 'evento'" not in sql
    assert "av.ativo   = true" in sql or "av.ativo = true" in sql
    assert resultado is True


@pytest.mark.asyncio
async def test_tem_acesso_event_sem_vinculo_retorna_false(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await membership_repo.tem_acesso_event(fake_pool, "u1", "ev1")
    assert resultado is False


@pytest.mark.asyncio
async def test_listar_events_acessiveis(fake_pool):
    id1, id2 = make_uuid(), make_uuid()
    fake_pool.set_fetch([{"id": id1}, {"id": id2}])

    resultado = await membership_repo.listar_events_acessiveis(fake_pool, "u1")

    assert resultado == [id1, id2]
    assert all(isinstance(x, str) for x in resultado)
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "scope = 'evento'" not in sql


@pytest.mark.asyncio
async def test_listar_events_acessiveis_detalhado_inclui_role(fake_pool):
    """Cada event carrega o nível efetivo (admin/moderador) da pessoa
    na arena dele — o frontend usa isso pra esconder ações que o nível
    atual não permite (docs/PERMISSOES_SPEC.md §7 item 5)."""
    fake_pool.set_fetch([
        {"id": "ev1", "nome": "Canal3 Expo", "slug": "canal3expo", "role": "admin"},
    ])

    resultado = await membership_repo.listar_events_acessiveis_detalhado(fake_pool, "u1")

    assert resultado[0]["role"] == "admin"
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "av.role" in sql


# ── listar_por_arenas (docs/PERMISSOES_SPEC.md §8.2) ───────────────────────────

@pytest.mark.asyncio
async def test_listar_por_arenas_filtra_scope_e_arena(fake_pool):
    m1 = make_uuid()
    fake_pool.set_fetch([
        {"id": make_uuid(), "user_id": "u1", "email": "a@x.com", "nome": "A",
         "scope": "marca", "arena_id": m1, "arena_nome": "Canal3",
         "role": "admin", "ativo": True, "criado_em": "2026-01-01"},
    ])

    resultado = await membership_repo.listar_por_arenas(fake_pool, [m1])

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "scope = 'marca'" in sql
    assert "arena_id = ANY($1" in sql
    assert len(resultado) == 1


@pytest.mark.asyncio
async def test_listar_por_arenas_vazio_nao_bate_no_banco(fake_pool):
    """Lista de arenas vazia (ex: moderador sem nenhuma arena onde é
    admin) retorna vazio sem nem montar a query — evita ANY($1) com
    array vazio precisar de tratamento especial."""
    resultado = await membership_repo.listar_por_arenas(fake_pool, [])

    assert resultado == []
    fake_pool.fetch.assert_not_called()


# ── auditoria ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_registrar_auditoria_grava_insert_append_only(fake_pool):
    await membership_repo.registrar_auditoria(
        fake_pool, "concedido", user_alvo_id="u1", realizado_por="dono@x.com",
        arena_id="m1", role="admin", detalhes={"origem": "teste"},
    )

    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    args = fake_pool.execute.call_args[0]
    assert "INSERT INTO membership_audit_log" in sql
    assert "UPDATE" not in sql and "DELETE" not in sql
    assert args[1:5] == ("concedido", "m1", "u1", "dono@x.com")


@pytest.mark.asyncio
async def test_registrar_auditoria_detalhes_none_nao_serializa(fake_pool):
    await membership_repo.registrar_auditoria(
        fake_pool, "revogado", user_alvo_id="u1", realizado_por="dono@x.com",
    )

    args = fake_pool.execute.call_args[0]
    assert args[-1] is None


@pytest.mark.asyncio
async def test_registrar_auditoria_user_alvo_id_none(fake_pool):
    """Migration 025: parceria acionada via bootstrap (Bearer
    <ADMIN_SECRET>, sem user_id de sessão real) — user_alvo_id vai
    None, realizado_por='admin' já identifica o ator."""
    await membership_repo.registrar_auditoria(
        fake_pool, "parceria_liberada", user_alvo_id=None, realizado_por="admin",
        arena_id="m1", role=None, detalhes={"arena_destino_id": "m2"},
    )

    args = fake_pool.execute.call_args[0]
    assert args[1:5] == ("parceria_liberada", "m1", None, "admin")


# ── revogar_todos_do_usuario (EXCLUSAO_CONTA_SPEC.md decisão #3) ────────────────

@pytest.mark.asyncio
async def test_revogar_todos_do_usuario(fake_pool):
    user_id = make_uuid()
    await membership_repo.revogar_todos_do_usuario(fake_pool, user_id)

    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    assert "UPDATE memberships SET ativo = false" in sql
    assert "user_id = $1" in sql
    assert "DELETE" not in sql
