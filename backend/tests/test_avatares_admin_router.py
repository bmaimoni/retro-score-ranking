"""
Testes de routers/avatares_admin.py — CRUD exclusivo de super-admin.
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


def admin_ctx(marca_id=None):
    return AdminContext(
        identificador="admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id or make_uuid(), "nivel": "admin"}],
    )


def _avatar(**overrides):
    base = {
        "id": make_uuid(), "nome": "Robô", "url": "https://cdn/robo.png",
        "ativo": True, "criado_em": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Restrito a super ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_comum_nao_lista_avatares(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get("/api/admin/avatares")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_comum_nao_cria_avatar(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/avatares", json={"nome": "Robô", "url": "https://cdn/robo.png"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_comum_nao_atualiza_avatar(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/avatares/{make_uuid()}", json={"ativo": False})
    assert resp.status_code == 403


# ── Super ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_super_lista_avatares(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.avatar.listar_todos", AsyncMock(return_value=[_avatar()])):
        resp = await client.get("/api/admin/avatares")

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_super_cria_avatar(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.avatar.criar", AsyncMock(return_value=_avatar())):
        resp = await client.post("/api/admin/avatares", json={"nome": "Robô", "url": "https://cdn/robo.png"})

    assert resp.status_code == 201
    assert resp.json()["nome"] == "Robô"


@pytest.mark.asyncio
async def test_super_desativa_avatar(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    avatar_id = make_uuid()

    with patch("repositories.avatar.atualizar_ativo", AsyncMock(return_value=_avatar(id=avatar_id, ativo=False))):
        resp = await client.patch(f"/api/admin/avatares/{avatar_id}", json={"ativo": False})

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_avatar_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.avatar.atualizar_ativo", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/avatares/{make_uuid()}", json={"ativo": True})

    assert resp.status_code == 404
