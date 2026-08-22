"""
Testes de routers/admin_vinculos.py — só super-admin gerencia vínculos
de outros administradores. Criação é por e-mail (não user_id) — a
pessoa precisa já ter logado alguma vez.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

SUPER_CTX  = AdminContext(identificador="admin", user_id=None, super=True)
ESCOPADO_CTX = AdminContext(identificador="pessoa@x.com", user_id="u-escopado", super=False)


def make_uuid():
    return str(uuid.uuid4())


def _usuario(email="pessoa@x.com"):
    return {"id": make_uuid(), "email": email, "email_verified": True,
            "nome": "Pessoa", "foto_url": None, "status": "ativo"}


def _vinculo(**overrides):
    base = {
        "id": make_uuid(), "user_id": make_uuid(), "escopo": "evento",
        "marca_id": None, "evento_id": make_uuid(), "ativo": True,
        "criado_em": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Acesso restrito a super-admin ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_escopado_nao_pode_listar_vinculos(client):
    app.dependency_overrides[require_admin] = lambda: ESCOPADO_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get("/api/admin/vinculos")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_escopado_nao_pode_criar_vinculo(client):
    app.dependency_overrides[require_admin] = lambda: ESCOPADO_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "novo@x.com", "escopo": "super"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_pode_listar_vinculos(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.admin_vinculo.listar_todos", AsyncMock(return_value=[_vinculo()])):
        resp = await client.get("/api/admin/vinculos")

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── Criar vínculo (por e-mail) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_vinculo_super(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.criar", AsyncMock(return_value=_vinculo(escopo="super", evento_id=None))):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "super"})

    assert resp.status_code == 201
    assert resp.json()["escopo"] == "super"


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
         patch("repositories.admin_vinculo.criar", AsyncMock(return_value=_vinculo(escopo="super", evento_id=None))):
        await client.post("/api/admin/vinculos",
            json={"email": "  Pessoa@X.com  ", "escopo": "super"})

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
            json={"email": "nunca-logou@x.com", "escopo": "super"})

    assert resp.status_code == 404
    assert "logar" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_criar_vinculo_marca_sem_marca_id_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "marca"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_evento_sem_evento_id_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "evento"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_super_com_evento_id_retorna_422(client):
    """super não aceita marca_id/evento_id junto — inconsistência clara."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "super", "evento_id": make_uuid()})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_escopo_invalido_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "raiz-do-sistema"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_email_invalido_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "nao-e-email", "escopo": "super"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_evento_inexistente_retorna_404(client):
    """Usuário existe, mas o evento_id apontado não — FK falha no banco."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.criar",
               AsyncMock(side_effect=Exception("violates foreign key constraint"))):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "evento", "evento_id": make_uuid()})

    assert resp.status_code == 404


# ── Atualizar (ativar/desativar) vínculo ────────────────────────────────────────

@pytest.mark.asyncio
async def test_desativar_vinculo(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()

    with patch("repositories.admin_vinculo.atualizar_ativo",
               AsyncMock(return_value=_vinculo(id=vinculo_id, ativo=False))):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_vinculo_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.admin_vinculo.atualizar_ativo", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{make_uuid()}", json={"ativo": True})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_escopado_nao_pode_atualizar_vinculo(client):
    app.dependency_overrides[require_admin] = lambda: ESCOPADO_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/vinculos/{make_uuid()}", json={"ativo": False})
    assert resp.status_code == 403
