"""
Testes de GET /api/admin/arenas/{arena_id}/wizard-status — Fase 9
(ARENA_SPEC.md E.1). Progresso calculado on-the-fly, sem tabela nova.
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


def _arena(**overrides):
    base = {
        "id": make_uuid(), "nome": "Liga dos Amigos", "slug": "liga-dos-amigos",
        "cor_primaria": None, "tipografia": None, "logo_url": None,
        "itens_por_pagina": None, "criado_em": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_wizard_status_sem_evento_sem_colaborador_sem_branding(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena_id = make_uuid()
    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.listar_events_da_arena", AsyncMock(return_value=[])), \
         patch("repositories.membership.listar_por_arenas", AsyncMock(return_value=[])):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/wizard-status")

    assert resp.status_code == 200
    assert resp.json() == {"tem_evento": False, "tem_colaborador": False, "tem_branding": False}


@pytest.mark.asyncio
async def test_wizard_status_com_evento_colaborador_e_branding(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena_id = make_uuid()
    dono_id, colega_id = make_uuid(), make_uuid()
    with patch("repositories.arena.buscar_por_id",
               AsyncMock(return_value=_arena(id=arena_id, cor_primaria="#5e2b82"))), \
         patch("repositories.arena.listar_events_da_arena",
               AsyncMock(return_value=[{"id": make_uuid(), "nome": "Torneio de Verão"}])), \
         patch("repositories.membership.listar_por_arenas", AsyncMock(return_value=[
             {"user_id": dono_id, "ativo": True, "role": "admin"},
             {"user_id": colega_id, "ativo": True, "role": "moderador"},
         ])):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/wizard-status")

    assert resp.status_code == 200
    assert resp.json() == {"tem_evento": True, "tem_colaborador": True, "tem_branding": True}


@pytest.mark.asyncio
async def test_wizard_status_colaborador_inativo_nao_conta(client):
    """membership revogado (ativo=false) não conta como colaborador —
    só o dono continua ativo, tem_colaborador deve ficar False."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena_id = make_uuid()
    dono_id, ex_colega_id = make_uuid(), make_uuid()
    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.listar_events_da_arena", AsyncMock(return_value=[])), \
         patch("repositories.membership.listar_por_arenas", AsyncMock(return_value=[
             {"user_id": dono_id, "ativo": True, "role": "admin"},
             {"user_id": ex_colega_id, "ativo": False, "role": "moderador"},
         ])):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/wizard-status")

    assert resp.status_code == 200
    assert resp.json()["tem_colaborador"] is False


@pytest.mark.asyncio
async def test_wizard_status_arena_nao_encontrada_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.get(f"/api/admin/arenas/{make_uuid()}/wizard-status")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wizard_status_sem_acesso_retorna_403(client):
    """admin comum sem vínculo nesta arena — 403, mesmo padrão de
    outros endpoints escopados de arenas_admin.py."""
    escopado = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": "outra-arena", "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena_id = make_uuid()
    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/wizard-status")

    assert resp.status_code == 403
