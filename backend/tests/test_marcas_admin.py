"""
Testes do router admin de marcas — /api/admin/marcas.
Ver docs/MARCAS_SPEC.md §3.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin

ADMIN_SECRET = "test-secret"
AUTH_HEADER  = {"Authorization": f"Bearer {ADMIN_SECRET}"}


def make_uuid():
    return str(uuid.uuid4())


def _marca(**overrides):
    base = {
        "id": make_uuid(), "nome": "Canal3", "slug": "canal3",
        "cor_primaria": "#5e2b82", "tipografia": "arcade",
        "logo_url": "https://cdn/canal3-logo.png", "criado_em": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides[require_admin] = lambda: ADMIN_SECRET
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Criar marca ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_marca(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.criar", AsyncMock(return_value=_marca())):
        resp = await client.post("/api/admin/marcas",
            json={"nome": "Canal3", "slug": "canal3", "cor_primaria": "#5e2b82",
                  "tipografia": "arcade", "logo_url": "https://cdn/canal3-logo.png"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["slug"] == "canal3"


@pytest.mark.asyncio
async def test_criar_marca_sem_campos_opcionais(client):
    """cor_primaria/tipografia/logo_url são opcionais na criação."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_minima = _marca(cor_primaria=None, tipografia=None, logo_url=None)

    with patch("repositories.marca.criar", AsyncMock(return_value=marca_minima)):
        resp = await client.post("/api/admin/marcas",
            json={"nome": "Marca Nova", "slug": "marca-nova"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_criar_marca_tipografia_invalida_retorna_422(client):
    """CHECK do banco tem uma segunda linha de defesa aqui, no Pydantic —
    422 antes de chegar no banco."""
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/marcas",
        json={"nome": "X", "slug": "x", "tipografia": "comic-sans"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_marca_slug_duplicado_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.criar",
               AsyncMock(side_effect=Exception("duplicate key value violates unique constraint"))):
        resp = await client.post("/api/admin/marcas",
            json={"nome": "Dup", "slug": "canal3"},
            headers=AUTH_HEADER)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_criar_marca_sem_auth_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/marcas", json={"nome": "X", "slug": "x"})
    assert resp.status_code == 401


# ── Listar marcas ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_marcas(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.listar_todas", AsyncMock(return_value=[_marca()])):
        resp = await client.get("/api/admin/marcas", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── Atualizar marca ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_cor_da_marca(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    atualizada = _marca(cor_primaria="#ff0000")

    with patch("repositories.marca.atualizar", AsyncMock(return_value=atualizada)):
        resp = await client.patch(f"/api/admin/marcas/{make_uuid()}",
            json={"cor_primaria": "#ff0000"},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["cor_primaria"] == "#ff0000"


@pytest.mark.asyncio
async def test_atualizar_marca_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.atualizar", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/marcas/{make_uuid()}",
            json={"nome": "X"},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_atualizar_marca_tipografia_invalida_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/marcas/{make_uuid()}",
        json={"tipografia": "papyrus"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


# ── Eventos da marca ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_eventos_da_marca(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_id = make_uuid()

    eventos = [
        {"id": make_uuid(), "nome": "Canal3 Expo 2026", "slug": "canal3expo-2026",
         "ativo": True, "publico": True, "criado_em": "2026-01-01"},
    ]
    with patch("repositories.marca.listar_eventos_da_marca", AsyncMock(return_value=eventos)):
        resp = await client.get(f"/api/admin/marcas/{marca_id}/eventos", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1
