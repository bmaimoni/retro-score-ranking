"""
Testes de repositories/admin_vinculo.py — CRUD e a função de checagem
de acesso, que é o coração da autorização escopada.

Ver docs/PERMISSOES_SPEC.md (migration 019 — nivel por marca,
escopo='evento' eliminado).
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
         "marca_id": None, "nivel": None, "ativo": True, "criado_em": "2026-01-01"},
    ])

    resultado = await admin_vinculo_repo.listar_por_usuario(fake_pool, "u1")

    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "ativo = true" in sql
    assert len(resultado) == 1


@pytest.mark.asyncio
async def test_criar_vinculo_super(fake_pool):
    fake_pool.set_fetchrow({
        "id": make_uuid(), "user_id": "u1", "escopo": "super",
        "marca_id": None, "nivel": None, "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await admin_vinculo_repo.criar(fake_pool, "u1", "super")

    assert resultado["escopo"] == "super"
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("u1", "super", None, None)


@pytest.mark.asyncio
async def test_criar_vinculo_marca_com_nivel(fake_pool):
    fake_pool.set_fetchrow({
        "id": make_uuid(), "user_id": "u1", "escopo": "marca",
        "marca_id": "m1", "nivel": "moderador", "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await admin_vinculo_repo.criar(fake_pool, "u1", "marca", nivel="moderador", marca_id="m1")

    assert resultado["nivel"] == "moderador"
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("u1", "marca", "m1", "moderador")


@pytest.mark.asyncio
async def test_criar_vinculo_e_idempotente_via_on_conflict(fake_pool):
    """A query usa ON CONFLICT ... DO UPDATE SET ativo=true, nivel=$4 —
    reativa (e atualiza nível) em vez de duplicar."""
    fake_pool.set_fetchrow({
        "id": make_uuid(), "user_id": "u1", "escopo": "marca",
        "marca_id": "m1", "nivel": "admin", "ativo": True, "criado_em": "2026-01-01",
    })

    await admin_vinculo_repo.criar(fake_pool, "u1", "marca", nivel="admin", marca_id="m1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET ativo = true, nivel = $4" in sql


@pytest.mark.asyncio
async def test_atualizar_ativo_desativa_sem_delete(fake_pool):
    fake_pool.set_fetchrow({
        "id": "v1", "user_id": "u1", "escopo": "marca",
        "marca_id": "m1", "nivel": "admin", "ativo": False, "criado_em": "2026-01-01",
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


@pytest.mark.asyncio
async def test_buscar_por_id(fake_pool):
    fake_pool.set_fetchrow({
        "id": "v1", "user_id": "u1", "escopo": "marca",
        "marca_id": "m1", "nivel": "admin", "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await admin_vinculo_repo.buscar_por_id(fake_pool, "v1")

    assert resultado["nivel"] == "admin"


@pytest.mark.asyncio
async def test_buscar_por_id_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await admin_vinculo_repo.buscar_por_id(fake_pool, "nao-existe")
    assert resultado is None


# ── tem_vinculo_admin_ativo: pré-requisito da transferência de titularidade ────

@pytest.mark.asyncio
async def test_tem_vinculo_admin_ativo_true(fake_pool):
    fake_pool.set_fetchrow({"?column?": 1})
    resultado = await admin_vinculo_repo.tem_vinculo_admin_ativo(fake_pool, "u1", "m1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "nivel = 'admin'" in sql
    assert "ativo = true" in sql
    assert resultado is True


@pytest.mark.asyncio
async def test_tem_vinculo_admin_ativo_false_quando_so_moderador(fake_pool):
    """A query já filtra nivel='admin' — um vínculo moderador não conta
    (moderador nunca vira titular sem antes virar admin)."""
    fake_pool.set_fetchrow(None)
    resultado = await admin_vinculo_repo.tem_vinculo_admin_ativo(fake_pool, "u1", "m1")
    assert resultado is False


# ── tem_acesso_evento: a query central de autorização ──────────────────────────

@pytest.mark.asyncio
async def test_tem_acesso_evento_cobre_super_e_marca_na_mesma_query(fake_pool):
    """
    Confirma que a query cobre super OR marca-bate numa query só, sem
    N+1. escopo='evento' foi eliminado (migration 019) — não deve mais
    aparecer na query.
    """
    fake_pool.set_fetchrow({"?column?": 1})

    resultado = await admin_vinculo_repo.tem_acesso_evento(fake_pool, "u1", "ev1")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "escopo = 'super'" in sql
    assert "escopo = 'marca'" in sql
    assert "escopo = 'evento'" not in sql
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
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "escopo = 'evento'" not in sql


@pytest.mark.asyncio
async def test_listar_eventos_acessiveis_detalhado_inclui_nivel(fake_pool):
    """Cada evento carrega o nível efetivo (admin/moderador) da pessoa
    na marca dele — o frontend usa isso pra esconder ações que o nível
    atual não permite (docs/PERMISSOES_SPEC.md §7 item 5)."""
    fake_pool.set_fetch([
        {"id": "ev1", "nome": "Canal3 Expo", "slug": "canal3expo", "nivel": "admin"},
    ])

    resultado = await admin_vinculo_repo.listar_eventos_acessiveis_detalhado(fake_pool, "u1")

    assert resultado[0]["nivel"] == "admin"
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "av.nivel" in sql


# ── auditoria ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_registrar_auditoria_grava_insert_append_only(fake_pool):
    await admin_vinculo_repo.registrar_auditoria(
        fake_pool, "concedido", user_alvo_id="u1", realizado_por="dono@x.com",
        marca_id="m1", nivel="admin", detalhes={"origem": "teste"},
    )

    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    args = fake_pool.execute.call_args[0]
    assert "INSERT INTO admin_vinculos_auditoria" in sql
    assert "UPDATE" not in sql and "DELETE" not in sql
    assert args[1:5] == ("concedido", "m1", "u1", "dono@x.com")


@pytest.mark.asyncio
async def test_registrar_auditoria_detalhes_none_nao_serializa(fake_pool):
    await admin_vinculo_repo.registrar_auditoria(
        fake_pool, "revogado", user_alvo_id="u1", realizado_por="dono@x.com",
    )

    args = fake_pool.execute.call_args[0]
    assert args[-1] is None
