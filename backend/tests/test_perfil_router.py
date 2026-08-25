"""
Testes de routers/perfil.py — exige sessão de visitante logado (não admin).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool

SESSION_COOKIE = "canal3_session"


def make_uuid():
    return str(uuid.uuid4())


def _usuario_sessao(user_id=None):
    return {"id": user_id or make_uuid(), "email": "p@x.com", "nome": "Pessoa"}


def _perfil(**overrides):
    base = {
        "id": make_uuid(), "email": "p@x.com", "nome": "Pessoa", "foto_url": None,
        "status": "ativo", "nome_completo": None, "data_nascimento": None,
        "cidade": None, "estado": None, "telefone": None, "avatar_id": None,
        "criado_em": "2026-01-01T00:00:00", "ultimo_login_em": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


# ── GET /api/perfil ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ver_perfil_sem_sessao_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/perfil")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ver_perfil_com_sessao(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    perfil = _perfil(id=usuario["id"])

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.usuario.buscar_perfil", AsyncMock(return_value=perfil)):
        resp = await client.get("/api/perfil")

    assert resp.status_code == 200
    assert resp.json()["id"] == usuario["id"]


# ── PATCH /api/perfil ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_perfil_sem_sessao_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.patch("/api/perfil", json={"cidade": "São Paulo"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_atualizar_perfil_campos_basicos(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    perfil_atualizado = _perfil(id=usuario["id"], cidade="São Paulo", estado="SP")

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.usuario.atualizar_perfil", AsyncMock(return_value=perfil_atualizado)) as mock:
        resp = await client.patch("/api/perfil", json={"cidade": "São Paulo", "estado": "SP"})

    assert resp.status_code == 200
    assert resp.json()["cidade"] == "São Paulo"
    mock.assert_called_once_with(pool, usuario["id"], {"cidade": "São Paulo", "estado": "SP"})


@pytest.mark.asyncio
async def test_atualizar_perfil_com_avatar_valido(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    avatar_id = make_uuid()
    avatar = {"id": avatar_id, "nome": "Robô", "url": "https://cdn/robo.png", "ativo": True, "criado_em": "2026-01-01"}
    perfil_atualizado = _perfil(id=usuario["id"], avatar_id=avatar_id)

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.avatar.buscar_por_id", AsyncMock(return_value=avatar)), \
         patch("repositories.usuario.atualizar_perfil", AsyncMock(return_value=perfil_atualizado)):
        resp = await client.patch("/api/perfil", json={"avatar_id": avatar_id})

    assert resp.status_code == 200
    assert resp.json()["avatar_id"] == avatar_id


@pytest.mark.asyncio
async def test_atualizar_perfil_com_avatar_inexistente_retorna_422(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.avatar.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch("/api/perfil", json={"avatar_id": make_uuid()})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_atualizar_perfil_com_avatar_desativado_retorna_422(client):
    """Avatar desativado não pode ser escolhido dali pra frente — quem
    já tinha continua com ele (não mexe no que já está setado)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    avatar_id = make_uuid()
    avatar_inativo = {"id": avatar_id, "nome": "Robô", "url": "https://cdn/robo.png", "ativo": False, "criado_em": "2026-01-01"}

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.avatar.buscar_por_id", AsyncMock(return_value=avatar_inativo)):
        resp = await client.patch("/api/perfil", json={"avatar_id": avatar_id})

    assert resp.status_code == 422
