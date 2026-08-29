"""
Testes de POST/GET/PATCH /api/admin/arenas/{id}/convites — convite
assíncrono de coadministração (Fase 10, ARENA_SPEC.md Fase F + H.1).

Cobertura: quem pode convidar (mesma régua de conceder vínculo direto),
auto-convite bloqueado, colaborador existente bloqueado, dedup de
convite pendente, rate limit de envio, falha de e-mail não deixa
convite "fantasma" sem aviso, e cancelamento restrito a quem convidou.
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


def _arena(**overrides):
    base = {"id": ARENA_A, "nome": "Liga dos Amigos", "slug": "liga-dos-amigos"}
    base.update(overrides)
    return base


def _convite(**overrides):
    base = {
        "id": make_uuid(), "arena_id": ARENA_A, "role": "admin",
        "email": "convidado@x.com", "invited_by": None,
        "expires_at": "2026-02-01T00:00:00", "criado_em": "2026-01-25T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── POST — criar convite ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_convite_fluxo_feliz(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(invited_by=ctx.user_id)
    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)), \
         patch("repositories.membership.buscar_convite_pendente_por_email", AsyncMock(return_value=None)), \
         patch("repositories.membership.contar_convites_por_remetente_ultimas_24h", AsyncMock(return_value=0)), \
         patch("auth.service.gerar_token_magic_link", return_value=("token-puro", "hash123")), \
         patch("repositories.membership.criar_convite", AsyncMock(return_value=convite)) as criar_mock, \
         patch("services.convite_email.enviar_email_convite", AsyncMock(return_value=None)) as email_mock, \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)) as auditoria_mock:

        resp = await client.post(
            f"/api/admin/arenas/{ARENA_A}/convites",
            json={"email": "Convidado@X.com", "role": "admin"},
        )

    assert resp.status_code == 201
    assert resp.json()["email"] == "convidado@x.com"
    criar_mock.assert_called_once()
    assert criar_mock.call_args[0][3] == "convidado@x.com"  # e-mail normalizado
    email_mock.assert_called_once()
    auditoria_mock.assert_called_once()
    assert auditoria_mock.call_args.kwargs["acao"] == "convite_enviado"


@pytest.mark.asyncio
async def test_criar_convite_bloqueia_moderador(client):
    """Moderador não pode convidar — mesma régua de _exigir_admin_na_arena
    (só admin da própria Arena ou super)."""
    ctx = moderador_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())):
        resp = await client.post(
            f"/api/admin/arenas/{ARENA_A}/convites",
            json={"email": "convidado@x.com", "role": "admin"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_criar_convite_bloqueia_admin_de_outra_arena(client):
    outra_arena = make_uuid()
    ctx = admin_ctx(arena_id=outra_arena)
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())):
        resp = await client.post(
            f"/api/admin/arenas/{ARENA_A}/convites",
            json={"email": "convidado@x.com", "role": "admin"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_criar_convite_bloqueia_auto_convite(client):
    ctx = admin_ctx(email="admin-a@x.com")
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())):
        resp = await client.post(
            f"/api/admin/arenas/{ARENA_A}/convites",
            json={"email": "Admin-A@X.com", "role": "admin"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_convite_bloqueia_quem_ja_colabora(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    usuario_existente = {"id": make_uuid(), "email": "convidado@x.com"}
    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario_existente)), \
         patch("repositories.membership.tem_vinculo_ativo", AsyncMock(return_value=True)):

        resp = await client.post(
            f"/api/admin/arenas/{ARENA_A}/convites",
            json={"email": "convidado@x.com", "role": "admin"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_convite_bloqueia_convite_pendente_duplicado(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)), \
         patch("repositories.membership.buscar_convite_pendente_por_email", AsyncMock(return_value=_convite())):

        resp = await client.post(
            f"/api/admin/arenas/{ARENA_A}/convites",
            json={"email": "convidado@x.com", "role": "admin"},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_criar_convite_rate_limit(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)), \
         patch("repositories.membership.buscar_convite_pendente_por_email", AsyncMock(return_value=None)), \
         patch("repositories.membership.contar_convites_por_remetente_ultimas_24h", AsyncMock(return_value=10)):

        resp = await client.post(
            f"/api/admin/arenas/{ARENA_A}/convites",
            json={"email": "convidado@x.com", "role": "admin"},
        )

    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_criar_convite_falha_envio_email_nao_grava_silenciosamente(client):
    """Se o Resend falhar, o admin precisa saber (502) — não pode achar
    que o convite foi enviado quando não foi."""
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(invited_by=ctx.user_id)
    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)), \
         patch("repositories.membership.buscar_convite_pendente_por_email", AsyncMock(return_value=None)), \
         patch("repositories.membership.contar_convites_por_remetente_ultimas_24h", AsyncMock(return_value=0)), \
         patch("auth.service.gerar_token_magic_link", return_value=("token-puro", "hash123")), \
         patch("repositories.membership.criar_convite", AsyncMock(return_value=convite)), \
         patch("services.convite_email.enviar_email_convite", AsyncMock(side_effect=RuntimeError("boom"))):

        resp = await client.post(
            f"/api/admin/arenas/{ARENA_A}/convites",
            json={"email": "convidado@x.com", "role": "admin"},
        )

    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_criar_convite_rejeita_role_invalido(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post(
        f"/api/admin/arenas/{ARENA_A}/convites",
        json={"email": "convidado@x.com", "role": "super"},
    )

    assert resp.status_code == 422


# ── GET — listar convites pendentes ─────────────────────────────────

@pytest.mark.asyncio
async def test_listar_convites_exige_admin_na_arena(client):
    ctx = moderador_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())):
        resp = await client.get(f"/api/admin/arenas/{ARENA_A}/convites")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_listar_convites_retorna_fila(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena())), \
         patch("repositories.membership.listar_convites_pendentes", AsyncMock(return_value=[_convite()])):
        resp = await client.get(f"/api/admin/arenas/{ARENA_A}/convites")

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── PATCH — cancelar convite ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancelar_convite_nao_encontrado(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.membership.buscar_convite_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/arenas/{ARENA_A}/convites/{make_uuid()}/cancelar")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancelar_convite_bloqueia_quem_nao_convidou(client):
    """F.6: só quem convidou (ou super) cancela — outro admin da mesma
    Arena não pode, mesmo tendo permissão de conceder."""
    ctx = admin_ctx(user_id=make_uuid())
    outro_admin_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(invited_by=outro_admin_id)
    with patch("repositories.membership.buscar_convite_por_id", AsyncMock(return_value=convite)):
        resp = await client.patch(f"/api/admin/arenas/{ARENA_A}/convites/{convite['id']}/cancelar")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cancelar_convite_permite_quem_convidou(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(invited_by=ctx.user_id)
    with patch("repositories.membership.buscar_convite_por_id", AsyncMock(return_value=convite)), \
         patch("repositories.membership.cancelar_convite", AsyncMock(return_value={**convite, "status": "cancelled"})), \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)) as auditoria_mock:

        resp = await client.patch(f"/api/admin/arenas/{ARENA_A}/convites/{convite['id']}/cancelar")

    assert resp.status_code == 200
    auditoria_mock.assert_called_once()
    assert auditoria_mock.call_args.kwargs["acao"] == "convite_cancelado"


@pytest.mark.asyncio
async def test_cancelar_convite_permite_super(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(invited_by=make_uuid())
    with patch("repositories.membership.buscar_convite_por_id", AsyncMock(return_value=convite)), \
         patch("repositories.membership.cancelar_convite", AsyncMock(return_value={**convite, "status": "cancelled"})), \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)):

        resp = await client.patch(f"/api/admin/arenas/{ARENA_A}/convites/{convite['id']}/cancelar")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cancelar_convite_ja_resolvido(client):
    ctx = admin_ctx()
    app.dependency_overrides[require_admin] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(invited_by=ctx.user_id)
    with patch("repositories.membership.buscar_convite_por_id", AsyncMock(return_value=convite)), \
         patch("repositories.membership.cancelar_convite", AsyncMock(return_value=None)):

        resp = await client.patch(f"/api/admin/arenas/{ARENA_A}/convites/{convite['id']}/cancelar")

    assert resp.status_code == 409
