"""
Testes de GET/POST /api/convites/{token} — preview público e aceite de
convite (Fase 10, ARENA_SPEC.md Fase F, decisão F.5). Cobertura
adversarial: token inválido/expirado, e-mail divergente da sessão
(sequestro de convite por link vazado), e aceite já resolvido.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_authenticated_user, AuthenticatedUser


def make_uuid():
    return str(uuid.uuid4())


def _convite(**overrides):
    base = {
        "id": make_uuid(), "arena_id": make_uuid(), "role": "admin",
        "email": "convidado@x.com", "invited_by": make_uuid(),
        "expires_at": "2026-02-01T00:00:00",
    }
    base.update(overrides)
    return base


def _usuario(email="convidado@x.com"):
    return {"id": make_uuid(), "email": email, "email_verified": True,
            "nome": "Convidado", "foto_url": None, "status": "ativo"}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_authenticated_user, None)


# ── GET /{token} — preview público ──────────────────────────────────

@pytest.mark.asyncio
async def test_preview_convite_valido(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    convite = _convite()
    arena = {"id": convite["arena_id"], "nome": "Liga dos Amigos"}

    with patch("repositories.membership.buscar_convite_valido_por_token_hash", AsyncMock(return_value=convite)), \
         patch("repositories.arena.buscar_por_id", AsyncMock(return_value=arena)):
        resp = await client.get("/api/convites/token-qualquer")

    assert resp.status_code == 200
    body = resp.json()
    assert body["arena_nome"] == "Liga dos Amigos"
    assert body["role"] == "admin"
    assert body["email"] == "convidado@x.com"


@pytest.mark.asyncio
async def test_preview_convite_invalido_ou_expirado(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.membership.buscar_convite_valido_por_token_hash", AsyncMock(return_value=None)):
        resp = await client.get("/api/convites/token-invalido")

    assert resp.status_code == 404


# ── POST /{token}/aceitar ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aceitar_convite_fluxo_feliz(client):
    usuario = _usuario()
    auth_user = AuthenticatedUser(user_id=usuario["id"], identificador=usuario["email"])
    app.dependency_overrides[require_authenticated_user] = lambda: auth_user
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(email="convidado@x.com")
    membership = {"id": make_uuid(), "user_id": usuario["id"], "scope": "marca",
                  "arena_id": convite["arena_id"], "role": "admin", "ativo": True}

    with patch("repositories.membership.buscar_convite_valido_por_token_hash", AsyncMock(return_value=convite)), \
         patch("auth.repository.buscar_usuario_por_id", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.aceitar_convite", AsyncMock(return_value=membership)), \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)) as auditoria_mock:

        resp = await client.post("/api/convites/token-valido/aceitar")

    assert resp.status_code == 200
    assert resp.json()["arena_id"] == convite["arena_id"]
    auditoria_mock.assert_called_once()
    assert auditoria_mock.call_args.kwargs["acao"] == "convite_aceito"
    assert auditoria_mock.call_args.kwargs["user_alvo_id"] == usuario["id"]


@pytest.mark.asyncio
async def test_aceitar_convite_email_divergente_bloqueado(client):
    """F.5: sessão válida, mas e-mail diferente do convidado — nunca
    aceita, mesmo com sessão real (evita sequestro de link vazado)."""
    usuario = _usuario(email="outra-pessoa@x.com")
    auth_user = AuthenticatedUser(user_id=usuario["id"], identificador=usuario["email"])
    app.dependency_overrides[require_authenticated_user] = lambda: auth_user
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(email="convidado@x.com")
    with patch("repositories.membership.buscar_convite_valido_por_token_hash", AsyncMock(return_value=convite)), \
         patch("auth.repository.buscar_usuario_por_id", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.aceitar_convite", AsyncMock()) as aceitar_mock:

        resp = await client.post("/api/convites/token-valido/aceitar")

    assert resp.status_code == 403
    aceitar_mock.assert_not_called()


@pytest.mark.asyncio
async def test_aceitar_convite_token_invalido(client):
    auth_user = AuthenticatedUser(user_id=make_uuid(), identificador="x@x.com")
    app.dependency_overrides[require_authenticated_user] = lambda: auth_user
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.membership.buscar_convite_valido_por_token_hash", AsyncMock(return_value=None)):
        resp = await client.post("/api/convites/token-invalido/aceitar")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_aceitar_convite_ja_resolvido_por_outro_caminho(client):
    """Corrida: token ainda parecia válido na leitura, mas já foi
    aceito/cancelado entre o SELECT e o UPDATE — aceitar_convite
    retorna None, endpoint não finge sucesso."""
    usuario = _usuario()
    auth_user = AuthenticatedUser(user_id=usuario["id"], identificador=usuario["email"])
    app.dependency_overrides[require_authenticated_user] = lambda: auth_user
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    convite = _convite(email="convidado@x.com")
    with patch("repositories.membership.buscar_convite_valido_por_token_hash", AsyncMock(return_value=convite)), \
         patch("auth.repository.buscar_usuario_por_id", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.aceitar_convite", AsyncMock(return_value=None)):

        resp = await client.post("/api/convites/token-valido/aceitar")

    assert resp.status_code == 409
