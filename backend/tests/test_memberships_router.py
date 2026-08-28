"""
Testes de routers/memberships.py — concessão/revogação de acesso
administrativo.

Ver docs/PERMISSOES_SPEC.md §2 (decisões #5, #9, #10, #12) e §5 (risco
#1 — escalonamento cross-arena exige teste adversarial explícito, não
só caminho feliz).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

SUPER_CTX = AdminContext(identificador="admin", user_id=None, super=True)


def make_uuid():
    return str(uuid.uuid4())


ARENA_A = make_uuid()
ARENA_B = make_uuid()


def admin_ctx(arena_id=ARENA_A, user_id=None, email="admin-a@x.com"):
    return AdminContext(
        identificador=email, user_id=user_id or make_uuid(), super=False,
        vinculos=[{"arena_id": arena_id, "role": "admin"}],
    )


def moderador_ctx(arena_id=ARENA_A, user_id=None, email="mod-a@x.com"):
    return AdminContext(
        identificador=email, user_id=user_id or make_uuid(), super=False,
        vinculos=[{"arena_id": arena_id, "role": "moderador"}],
    )


def _usuario(email="pessoa@x.com"):
    return {"id": make_uuid(), "email": email, "email_verified": True,
            "nome": "Pessoa", "foto_url": None, "status": "ativo"}


def _vinculo(**overrides):
    base = {
        "id": make_uuid(), "user_id": make_uuid(), "scope": "marca",
        "arena_id": ARENA_A, "role": "admin", "ativo": True,
        "criado_em": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


def _sem_auditoria():
    """Patch de registrar_auditoria pra testes que não checam auditoria
    diretamente — evita bater no pool real (MagicMock não-awaitable)."""
    return patch("repositories.membership.registrar_auditoria", AsyncMock())


# ── GET: super vê tudo; admin escopado só as próprias arenas (§8.2) ────────────

@pytest.mark.asyncio
async def test_super_admin_pode_listar_vinculos(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.membership.listar_todos", AsyncMock(return_value=[_vinculo()])):
        resp = await client.get("/api/admin/vinculos")

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_admin_escopado_lista_vinculos_da_propria_arena(client):
    """docs/PERMISSOES_SPEC.md §8.2: admin/dono de arena passa a ver os
    próprios vínculos (antes: 403 total, mesmo pra própria arena)."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    listar_mock = AsyncMock(return_value=[_vinculo(arena_id=ARENA_A)])

    with patch("repositories.membership.listar_por_arenas", listar_mock):
        resp = await client.get("/api/admin/vinculos")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    listar_mock.assert_called_once_with(pool, [ARENA_A])


@pytest.mark.asyncio
async def test_admin_de_arena_a_nao_recebe_vinculos_da_arena_b(client):
    """Adversarial (mesma régua do risco #1): a query escopada nunca
    inclui arena fora do que o próprio admin administra."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    listar_mock = AsyncMock(return_value=[])

    with patch("repositories.membership.listar_por_arenas", listar_mock):
        await client.get("/api/admin/vinculos")

    arena_ids_pedidos = listar_mock.call_args[0][1]
    assert ARENA_B not in arena_ids_pedidos


@pytest.mark.asyncio
async def test_moderador_nao_ve_nenhum_vinculo(client):
    """Moderador não gerencia vínculo em lugar nenhum — a arena onde
    ele só é moderador não entra na lista de arenas consultadas."""
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    listar_mock = AsyncMock(return_value=[])

    with patch("repositories.membership.listar_por_arenas", listar_mock):
        resp = await client.get("/api/admin/vinculos")

    assert resp.status_code == 200
    assert resp.json() == []
    listar_mock.assert_called_once_with(pool, [])


# ── Criar vínculo (por e-mail) — super ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_vinculo_super_scope_super(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.criar", AsyncMock(return_value=_vinculo(scope="super", arena_id=None, role=None))), \
         _sem_auditoria():
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "scope": "super"})

    assert resp.status_code == 201
    assert resp.json()["scope"] == "super"


@pytest.mark.asyncio
async def test_criar_vinculo_arena_grava_auditoria(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    criar_mock = AsyncMock(return_value=_vinculo(scope="marca", arena_id=ARENA_A, role="moderador"))
    auditoria_mock = AsyncMock()
    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.criar", criar_mock), \
         patch("repositories.membership.registrar_auditoria", auditoria_mock):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "scope": "marca", "arena_id": ARENA_A, "role": "moderador"})

    assert resp.status_code == 201
    criar_mock.assert_called_once_with(pool, usuario["id"], "marca", "moderador", ARENA_A)
    auditoria_mock.assert_called_once_with(
        pool, acao="concedido", user_alvo_id=usuario["id"], realizado_por="admin",
        arena_id=ARENA_A, role="moderador",
    )


@pytest.mark.asyncio
async def test_criar_vinculo_email_normalizado_antes_da_busca(client):
    """E-mail com espaço/maiúsculas é normalizado antes de buscar —
    mesma normalização usada no login (AUTH_SPEC.md)."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario(email="pessoa@x.com")
    buscar_mock = AsyncMock(return_value=usuario)

    with patch("auth.repository.buscar_usuario_por_email", buscar_mock), \
         patch("repositories.membership.criar", AsyncMock(return_value=_vinculo(scope="super", arena_id=None, role=None))), \
         _sem_auditoria():
        await client.post("/api/admin/vinculos",
            json={"email": "  Pessoa@X.com  ", "scope": "super"})

    buscar_mock.assert_called_once_with(pool, "pessoa@x.com")


@pytest.mark.asyncio
async def test_criar_vinculo_pessoa_nunca_logou_retorna_404_com_mensagem_clara(client):
    """Não dá pra vincular alguém que nunca criou conta — mensagem
    explica o que fazer, não só '404 not found' genérico."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)):
        resp = await client.post("/api/admin/vinculos",
            json={"email": "nunca-logou@x.com", "scope": "super"})

    assert resp.status_code == 404
    assert "logar" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_criar_vinculo_arena_sem_arena_id_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "scope": "marca", "role": "admin"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_arena_sem_role_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "scope": "marca", "arena_id": make_uuid()})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_super_com_role_retorna_422(client):
    """super não aceita arena_id/role junto — inconsistência clara."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "scope": "super", "role": "admin"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_scope_invalido_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "scope": "raiz-do-sistema"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_scope_evento_nao_existe_mais_retorna_422(client):
    """scope='evento' foi eliminado na migration 019 — não é mais um
    valor aceito (era válido antes)."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "scope": "evento", "arena_id": make_uuid()})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_role_invalido_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "scope": "marca", "arena_id": make_uuid(), "role": "super-moderador"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_email_invalido_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "nao-e-email", "scope": "super"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_arena_inexistente_retorna_404(client):
    """Usuário existe, mas o arena_id apontado não — FK falha no banco."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.criar",
               AsyncMock(side_effect=Exception("violates foreign key constraint"))):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "scope": "marca", "arena_id": make_uuid(), "role": "admin"})

    assert resp.status_code == 404


# ── Criar vínculo — admin escopado (decisão #5) ─────────────────────────────────

@pytest.mark.asyncio
async def test_admin_concede_moderador_na_propria_arena(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.criar", AsyncMock(return_value=_vinculo(arena_id=ARENA_A, role="moderador"))), \
         _sem_auditoria():
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "scope": "marca", "arena_id": ARENA_A, "role": "moderador"})

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_concede_outro_admin_na_propria_arena(client):
    """Admin comum pode conceder nível admin (não só moderador) — a
    restrição de decisão #9 é só na REVOGAÇÃO de admin, não na concessão."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.criar", AsyncMock(return_value=_vinculo(arena_id=ARENA_A, role="admin"))), \
         _sem_auditoria():
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "scope": "marca", "arena_id": ARENA_A, "role": "admin"})

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_nao_pode_conceder_em_outra_arena(client):
    """Adversarial (risco #1 do PERMISSOES_SPEC.md): admin de A não
    pode conceder vínculo em B, mesmo enviando arena_id=B explicitamente."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "scope": "marca", "arena_id": ARENA_B, "role": "moderador"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_pode_conceder_scope_super(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos", json={"email": "x@x.com", "scope": "super"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_pode_conceder_nada(client):
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "scope": "marca", "arena_id": ARENA_A, "role": "moderador"})

    assert resp.status_code == 403


# ── Atualizar (ativar/desativar) vínculo — super ────────────────────────────────

@pytest.mark.asyncio
async def test_super_reativa_vinculo(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, ativo=False)

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=None)), \
         patch("repositories.membership.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": True})), \
         _sem_auditoria():
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": True})

    assert resp.status_code == 200
    assert resp.json()["ativo"] is True


@pytest.mark.asyncio
async def test_super_revoga_vinculo_super(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, scope="super", arena_id=None, role=None)

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.membership.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": False})), \
         _sem_auditoria():
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_vinculo_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{make_uuid()}", json={"ativo": True})

    assert resp.status_code == 404


# ── Atualizar vínculo — admin escopado ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_revoga_moderador_da_propria_arena(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, arena_id=ARENA_A, role="moderador")

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=None)), \
         patch("repositories.membership.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": False})), \
         _sem_auditoria():
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_comum_nao_revoga_outro_admin_da_arena(client):
    """Decisão #9: admin comum não revoga outro admin, nem da própria
    arena — só o titular ou super."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    outro_admin_user_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, user_id=outro_admin_user_id, arena_id=ARENA_A, role="admin")

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dono_revoga_outro_admin_da_arena(client):
    """Decisão #9: titular É capaz de revogar outro admin da própria arena."""
    owner_user_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A, user_id=owner_user_id)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    outro_admin_user_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, user_id=outro_admin_user_id, arena_id=ARENA_A, role="admin")

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=owner_user_id)), \
         patch("repositories.membership.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": False})), \
         _sem_auditoria():
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revogar_vinculo_do_titular_atual_retorna_409(client):
    """Decisão #10: revogar o vínculo do titular atual é bloqueado —
    mesmo pra super — até a titularidade ser transferida. Trava de
    integridade (arenas.owner_user_id ficaria órfão), não de permissão."""
    owner_user_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, user_id=owner_user_id, arena_id=ARENA_A, role="admin")

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=owner_user_id)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_admin_nao_revoga_vinculo_de_outra_arena(client):
    """Adversarial (risco #1): admin de A não revoga vínculo (nem
    moderador) de B, mesmo sabendo o vinculo_id."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, arena_id=ARENA_B, role="moderador")

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_revoga_vinculo_super(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, scope="super", arena_id=None, role=None)

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_reativa_vinculo_de_outra_arena(client):
    """Adversarial: reativação segue a mesma regra de concessão
    (própria arena só) — não só a de revogação."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, arena_id=ARENA_B, role="moderador", ativo=False)

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": True})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_revoga_ninguem(client):
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, arena_id=ARENA_A, role="moderador")

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_atualizar_vinculo_grava_auditoria_na_revogacao(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, arena_id=ARENA_A, role="moderador")
    auditoria_mock = AsyncMock()

    with patch("repositories.membership.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=None)), \
         patch("repositories.membership.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": False})), \
         patch("repositories.membership.registrar_auditoria", auditoria_mock):
        await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    auditoria_mock.assert_called_once_with(
        pool, acao="revogado", user_alvo_id=vinculo["user_id"], realizado_por="admin",
        arena_id=ARENA_A, role="moderador",
    )
