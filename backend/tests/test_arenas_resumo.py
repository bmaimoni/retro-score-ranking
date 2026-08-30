"""
Testes de GET /api/admin/arenas/{arena_id}/resumo — tela inicial do
painel (docs/PAINEIS_ADMIN_SPEC.md Fase 0, F0.3).
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
async def test_resumo_retorna_events_com_contagem(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena_id = make_uuid()
    events = [{
        "id": make_uuid(), "nome": "Torneio de Verão", "slug": "torneio-verao",
        "ativo": True, "publico": True, "data_inicio": "2026-01-01T00:00:00",
        "data_fim": "2026-02-01T00:00:00", "criado_em": "2026-01-01T00:00:00",
        "total_recordes": 12,
    }]
    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.listar_resumo_events_da_arena", AsyncMock(return_value=events)):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/resumo")

    assert resp.status_code == 200
    assert resp.json() == {"events": events}


@pytest.mark.asyncio
async def test_resumo_arena_nao_encontrada_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.get(f"/api/admin/arenas/{make_uuid()}/resumo")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resumo_sem_acesso_retorna_403(client):
    """admin comum sem vínculo nesta arena — 403, não vaza resumo de
    outra Arena (mesma disciplina de escopo das 3 auditorias de papel)."""
    escopado = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": "outra-arena", "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena_id = make_uuid()
    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/resumo")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resumo_admin_da_propria_arena_funciona(client):
    arena_id = make_uuid()
    escopado = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": arena_id, "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.listar_resumo_events_da_arena", AsyncMock(return_value=[])):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/resumo")

    assert resp.status_code == 200
    assert resp.json() == {"events": []}
