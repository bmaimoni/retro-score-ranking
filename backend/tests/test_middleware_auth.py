"""
Testes de middleware/auth.py — require_admin aceita dois caminhos
(ver docs/PERMISSOES_SPEC.md):
  1. Bearer <ADMIN_SECRET> — sempre super-admin (bootstrap).
  2. Sessão de visitante com membership — nível por arena (não mais
     por evento — scope='evento' foi eliminado na migration 019).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext
from config import get_settings

AUTH_HEADER = {"Authorization": "Bearer test-secret-123"}

# /api/admin/feed é usado aqui só como "qualquer rota protegida" pra
# exercitar require_admin — os filtros combináveis (BACKLOG_2026.md
# §4.1/4.4) não são o foco deste arquivo, mas o kwarg completo precisa
# bater pra assert_called_once_with não quebrar.
FILTROS_FEED_VAZIOS = dict(
    status=None, data_de=None, data_ate=None, game_id=None,
    sem_foto=False, sem_identificacao=False, busca=None,
)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    get_settings.cache_clear()


def _rota_teste_protegida():
    """Usa /api/admin/feed como rota real pra exercitar require_admin de
    ponta a ponta (não é o foco do teste, só precisa de QUALQUER rota
    que dependa de require_admin)."""
    return "/api/admin/feed"


# ── Caminho 1: Bearer token ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bearer_correto_e_sempre_super(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", "test-secret-123")
    get_settings.cache_clear()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.entry.listar_feed_admin", AsyncMock(return_value=[])), \
         patch("repositories.entry.contar_feed_admin",  AsyncMock(return_value=0)) as contar_mock:
        resp = await client.get(_rota_teste_protegida(), headers=AUTH_HEADER)

    assert resp.status_code == 200
    # Super-admin sem event_id na URL → event_ids=None (vê tudo, como sempre)
    contar_mock.assert_called_once_with(pool, event_ids=None, **FILTROS_FEED_VAZIOS)


@pytest.mark.asyncio
async def test_bearer_errado_retorna_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", "test-secret-123")
    get_settings.cache_clear()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get(_rota_teste_protegida(), headers={"Authorization": "Bearer errado"})
    assert resp.status_code == 401


# ── Caminho 2: sessão + membership ────────────────────────────────────────

@pytest.mark.asyncio
async def test_sessao_sem_vinculo_retorna_401(client):
    """Pessoa logada normal (visitante), sem NENHUM membership —
    não vira admin só por ter sessão."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = {"id": "u1", "email": "visitante@x.com"}

    client.cookies.set("canal3_session", "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.listar_por_usuario", AsyncMock(return_value=[])):
        resp = await client.get(_rota_teste_protegida())

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sessao_com_vinculo_arena_funciona_escopado(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = {"id": "u1", "email": "admin-arena@x.com"}
    vinculo = {"id": "v1", "user_id": "u1", "scope": "marca",
               "arena_id": "m1", "role": "admin", "ativo": True, "criado_em": "2026-01-01"}

    client.cookies.set("canal3_session", "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.listar_por_usuario", AsyncMock(return_value=[vinculo])), \
         patch("repositories.membership.tem_acesso_event", AsyncMock(return_value=True)), \
         patch("repositories.entry.listar_feed_admin", AsyncMock(return_value=[])), \
         patch("repositories.entry.contar_feed_admin",  AsyncMock(return_value=0)) as contar_mock:
        resp = await client.get(f"{_rota_teste_protegida()}?event_id=ev1")

    assert resp.status_code == 200
    contar_mock.assert_called_once_with(pool, event_ids=["ev1"], **FILTROS_FEED_VAZIOS)


@pytest.mark.asyncio
async def test_sessao_com_vinculo_super(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = {"id": "u1", "email": "super@x.com"}
    vinculo = {"id": "v1", "user_id": "u1", "scope": "super",
               "arena_id": None, "role": None, "ativo": True, "criado_em": "2026-01-01"}

    client.cookies.set("canal3_session", "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.listar_por_usuario", AsyncMock(return_value=[vinculo])), \
         patch("repositories.entry.listar_feed_admin", AsyncMock(return_value=[])), \
         patch("repositories.entry.contar_feed_admin",  AsyncMock(return_value=0)) as contar_mock:
        # Nem precisa de event_id na URL — é super via sessão também
        resp = await client.get(_rota_teste_protegida())

    assert resp.status_code == 200
    contar_mock.assert_called_once_with(pool, event_ids=None, **FILTROS_FEED_VAZIOS)


@pytest.mark.asyncio
async def test_sem_bearer_e_sem_cookie_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get(_rota_teste_protegida())
    assert resp.status_code == 401


# ── AdminContext.__str__ (compat com logging) ────────────────────────────────

def test_admin_context_str_e_o_identificador():
    ctx = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    assert str(ctx) == "pessoa@x.com"


# ── AdminContext: nível por arena (docs/PERMISSOES_SPEC.md) ──────────────────

def test_super_e_admin_em_qualquer_arena():
    ctx = AdminContext(identificador="admin", user_id=None, super=True)
    assert ctx.role_na_arena("m-qualquer") == "admin"
    assert ctx.eh_admin_na_arena("m-qualquer") is True
    assert ctx.tem_acesso_na_arena("m-qualquer") is True


def test_role_na_arena_bate_com_vinculo_do_usuario():
    ctx = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": "m1", "role": "moderador"}],
    )
    assert ctx.role_na_arena("m1") == "moderador"
    assert ctx.eh_admin_na_arena("m1") is False
    assert ctx.tem_acesso_na_arena("m1") is True


def test_role_na_arena_fora_do_vinculo_e_none():
    """Admin de uma arena não tem nível nenhum noutra — isolamento
    cross-arena é a garantia central deste modelo."""
    ctx = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": "m1", "role": "admin"}],
    )
    assert ctx.role_na_arena("m2") is None
    assert ctx.eh_admin_na_arena("m2") is False
    assert ctx.tem_acesso_na_arena("m2") is False


def test_admin_pode_ter_roles_diferentes_em_arenas_diferentes():
    """Mesma pessoa: admin numa arena, moderador noutra — granularidade
    é por vínculo, não global (decisão #2 do PERMISSOES_SPEC.md)."""
    ctx = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[
            {"arena_id": "m1", "role": "admin"},
            {"arena_id": "m2", "role": "moderador"},
        ],
    )
    assert ctx.eh_admin_na_arena("m1") is True
    assert ctx.eh_admin_na_arena("m2") is False
    assert ctx.role_na_arena("m2") == "moderador"


@pytest.mark.asyncio
async def test_require_admin_monta_vinculos_so_com_scope_arena(client):
    """super via sessão não entra na lista de vinculos (nível por arena
    não se aplica a super) — só os vínculos scope='marca' viram
    entries em AdminContext.vinculos."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = {"id": "u1", "email": "pessoa@x.com"}
    vinculos = [
        {"id": "v1", "user_id": "u1", "scope": "marca",
         "arena_id": "m1", "role": "admin", "ativo": True, "criado_em": "2026-01-01"},
        {"id": "v2", "user_id": "u1", "scope": "marca",
         "arena_id": "m2", "role": "moderador", "ativo": True, "criado_em": "2026-01-01"},
    ]

    from middleware.auth import require_admin as _require_admin

    async def _fake_request():
        class FakeRequest:
            cookies = {"canal3_session": "sessao-valida"}
            headers = {}
        return FakeRequest()

    request = await _fake_request()
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.listar_por_usuario", AsyncMock(return_value=vinculos)):
        ctx = await _require_admin(request, pool)

    assert ctx.super is False
    assert ctx.eh_admin_na_arena("m1") is True
    assert ctx.eh_admin_na_arena("m2") is False
    assert ctx.role_na_arena("m2") == "moderador"
