"""
Testes do router admin de placares — /api/admin/placares.
Ver docs/EVENTOS_SPEC.md §3, decisão #2 (entidade nomeada e persistida).
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


def _placar():
    return {"id": make_uuid(), "nome": "Temporada 2026", "slug": "temporada-2026",
            "escopo": "customizado", "criado_em": "2026-01-01T00:00:00"}


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides[require_admin] = lambda: ADMIN_SECRET
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Criar placar customizado ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_placar_customizado(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.criar", AsyncMock(return_value=_placar())):
        resp = await client.post("/api/admin/placares",
            json={"nome": "Temporada 2026", "slug": "temporada-2026"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["escopo"] == "customizado"


@pytest.mark.asyncio
async def test_criar_placar_slug_duplicado_retorna_409(client):
    """Cobre também a tentativa de criar um segundo placar 'global' —
    o índice único parcial do banco rejeita, e a mensagem de erro contém
    'unique' igual a qualquer outro conflito de slug."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.criar",
               AsyncMock(side_effect=Exception("duplicate key value violates unique constraint"))):
        resp = await client.post("/api/admin/placares",
            json={"nome": "Dup", "slug": "geral"},
            headers=AUTH_HEADER)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_criar_placar_sem_auth_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)
    resp = await client.post("/api/admin/placares", json={"nome": "X", "slug": "x"})
    assert resp.status_code == 401


# ── Listar placares ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_placares(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.listar_todos", AsyncMock(return_value=[_placar()])):
        resp = await client.get("/api/admin/placares", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── Membership de events ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adicionar_event_ao_placar(client):
    placar_id = make_uuid()
    event_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"placar_id": placar_id, "event_id": event_id, "ativo": True, "criado_em": "2026-01-01"}
    with patch("repositories.placar.adicionar_event", AsyncMock(return_value=vinculo)):
        resp = await client.post(f"/api/admin/placares/{placar_id}/events/{event_id}",
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["ativo"] is True


@pytest.mark.asyncio
async def test_remover_event_do_placar_via_patch_ativo_false(client):
    """
    'Remover' é ativo=false, não DELETE — app_user não tem permissão de
    DELETE em placar_eventos (ver migration 012).
    """
    placar_id = make_uuid()
    event_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"placar_id": placar_id, "event_id": event_id, "ativo": False, "criado_em": "2026-01-01"}
    with patch("repositories.placar.remover_event", AsyncMock(return_value=vinculo)) as remover_mock:
        resp = await client.patch(f"/api/admin/placares/{placar_id}/events/{event_id}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False
    remover_mock.assert_called_once_with(pool, placar_id, event_id)


@pytest.mark.asyncio
async def test_remover_event_inexistente_no_placar_retorna_404(client):
    placar_id = make_uuid()
    event_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.remover_event", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/placares/{placar_id}/events/{event_id}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reativar_event_no_placar(client):
    placar_id = make_uuid()
    event_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"placar_id": placar_id, "event_id": event_id, "ativo": True, "criado_em": "2026-01-01"}
    with patch("repositories.placar.adicionar_event", AsyncMock(return_value=vinculo)) as add_mock:
        resp = await client.patch(f"/api/admin/placares/{placar_id}/events/{event_id}",
            json={"ativo": True},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    add_mock.assert_called_once_with(pool, placar_id, event_id)


@pytest.mark.asyncio
async def test_listar_events_do_placar(client):
    placar_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    events = [
        {"id": make_uuid(), "nome": "Evento A", "slug": "event-a", "ativo": True,  "criado_em": "2026-01-01"},
        {"id": make_uuid(), "nome": "Evento B", "slug": "event-b", "ativo": False, "criado_em": "2026-01-02"},
    ]
    with patch("repositories.placar.listar_events_do_placar", AsyncMock(return_value=events)):
        resp = await client.get(f"/api/admin/placares/{placar_id}/events", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 2
