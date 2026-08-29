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


# ── Convite assíncrono de coadministração (Fase 10, ARENA_SPEC.md Fase F) ──────

@pytest.mark.asyncio
async def test_buscar_convite_pendente_por_email_filtra_status(fake_pool):
    fake_pool.set_fetchrow({"id": make_uuid(), "arena_id": "a1", "role": "admin",
                             "email": "x@x.com", "invited_by": "u1",
                             "expires_at": "2026-02-01", "criado_em": "2026-01-25"})

    resultado = await membership_repo.buscar_convite_pendente_por_email(fake_pool, "a1", "x@x.com")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "status = 'pending'" in sql
    assert resultado["email"] == "x@x.com"


@pytest.mark.asyncio
async def test_contar_convites_por_remetente_ultimas_24h_ignora_active(fake_pool):
    """Convite já aceito (status='active') não deveria contar contra o
    rate limit de novos envios pendentes/cancelados — a query filtra
    status != 'active' de propósito."""
    fake_pool.set_fetchval(2)

    resultado = await membership_repo.contar_convites_por_remetente_ultimas_24h(fake_pool, "a1", "u1")

    sql = " ".join(fake_pool.fetchval.call_args[0][0].split())
    assert "status != 'active'" in sql
    assert resultado == 2


@pytest.mark.asyncio
async def test_criar_convite_nasce_pending_inativo_sem_user_id(fake_pool):
    fake_pool.set_fetchrow({"id": make_uuid(), "arena_id": "a1", "role": "admin",
                             "status": "pending", "email": "x@x.com",
                             "invited_by": "u1", "expires_at": "2026-02-01",
                             "criado_em": "2026-01-25"})

    resultado = await membership_repo.criar_convite(
        fake_pool, "a1", "admin", "x@x.com", "u1", "hash123", 7,
    )

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "'pending'" in sql
    assert "false" in sql  # ativo=false
    assert resultado["status"] == "pending"


@pytest.mark.asyncio
async def test_listar_convites_pendentes_filtra_status(fake_pool):
    fake_pool.set_fetch([{"id": make_uuid(), "arena_id": "a1", "role": "admin",
                           "email": "x@x.com", "invited_by": "u1",
                           "expires_at": "2026-02-01", "criado_em": "2026-01-25"}])

    resultado = await membership_repo.listar_convites_pendentes(fake_pool, "a1")

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "status = 'pending'" in sql
    assert len(resultado) == 1


@pytest.mark.asyncio
async def test_buscar_convite_valido_por_token_hash_filtra_expiracao(fake_pool):
    fake_pool.set_fetchrow({"id": make_uuid(), "arena_id": "a1", "role": "admin",
                             "email": "x@x.com", "invited_by": "u1",
                             "expires_at": "2026-02-01"})

    resultado = await membership_repo.buscar_convite_valido_por_token_hash(fake_pool, "hash123")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "status = 'pending'" in sql
    assert "expires_at > now()" in sql
    assert resultado["email"] == "x@x.com"


@pytest.mark.asyncio
async def test_cancelar_convite_so_afeta_pending(fake_pool):
    fake_pool.set_fetchrow({"id": "c1", "arena_id": "a1", "role": "admin",
                             "email": "x@x.com", "invited_by": "u1", "criado_em": "2026-01-25"})

    resultado = await membership_repo.cancelar_convite(fake_pool, "c1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "status = 'cancelled'" in sql
    assert "token_hash = NULL" in sql
    assert "WHERE id = $1 AND status = 'pending'" in sql
    assert resultado["id"] == "c1"


@pytest.mark.asyncio
async def test_cancelar_convite_ja_resolvido_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)

    resultado = await membership_repo.cancelar_convite(fake_pool, "c1")

    assert resultado is None


@pytest.mark.asyncio
async def test_aceitar_convite_ativa_membership(fake_pool):
    fake_pool.set_fetchrow({"id": "c1", "user_id": "u2", "scope": "marca",
                             "arena_id": "a1", "role": "admin", "ativo": True,
                             "criado_em": "2026-01-25"})

    resultado = await membership_repo.aceitar_convite(fake_pool, "c1", "u2")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "status = 'active'" in sql
    assert "ativo = true" in sql
    assert "token_hash = NULL" in sql
    assert "WHERE id = $1 AND status = 'pending'" in sql
    assert resultado["user_id"] == "u2"


@pytest.mark.asyncio
async def test_tem_vinculo_ativo_scoped_a_marca_e_ativo(fake_pool):
    fake_pool.set_fetchrow({"1": 1})

    resultado = await membership_repo.tem_vinculo_ativo(fake_pool, "u1", "a1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "scope = 'marca'" in sql
    assert "ativo = true" in sql
    assert resultado is True
