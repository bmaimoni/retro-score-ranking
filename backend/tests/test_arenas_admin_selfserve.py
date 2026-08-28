"""
Testes do caminho self-serve de POST /api/admin/arenas — Fase 8
(ARENA_SPEC.md Fases B, D, G). Cobertura adversarial: rate limit,
colisão de nome, heurística de risco, isenção de super, e fluxo feliz
completo (usuário comum vira admin+dono da própria arena).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, require_super_or_authenticated_user, AdminContext

SUPER_CTX = AdminContext(identificador="admin", user_id=None, super=True)


def make_uuid():
    return str(uuid.uuid4())


def usuario_comum_ctx(user_id=None):
    return AdminContext(identificador="pessoa@example.com", user_id=user_id or make_uuid(), super=False)


def _arena(**overrides):
    base = {
        "id": make_uuid(), "nome": "Liga dos Amigos", "slug": "liga-dos-amigos",
        "cor_primaria": None, "tipografia": None, "logo_url": None,
        "status": "published", "plan": "free", "criado_em": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_super_or_authenticated_user, None)


@pytest.mark.asyncio
async def test_selfserve_fluxo_feliz_vira_admin_e_dono_automaticamente(client):
    ctx = usuario_comum_ctx()
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena = _arena(status="published")
    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=0)), \
         patch("repositories.arena.listar_nome_slug", AsyncMock(return_value=[])), \
         patch("repositories.arena.criar", AsyncMock(return_value=arena)) as criar_mock, \
         patch("repositories.membership.criar", AsyncMock(return_value={})) as membership_criar_mock, \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)), \
         patch("repositories.arena.transferir_titularidade", AsyncMock(return_value={**arena, "owner_user_id": ctx.user_id})):

        resp = await client.post("/api/admin/arenas",
            json={"nome": "Liga dos Amigos", "slug": "liga-dos-amigos"})

    assert resp.status_code == 201
    assert resp.json()["owner_user_id"] == ctx.user_id
    # nasce published — não disparou nenhum sinal de risco
    criar_mock.assert_called_once()
    assert criar_mock.call_args.kwargs.get("status") == "published"
    membership_criar_mock.assert_called_once()
    assert membership_criar_mock.call_args[0][1] == ctx.user_id
    assert membership_criar_mock.call_args[0][2] == "marca"
    assert membership_criar_mock.call_args[0][3] == "admin"


@pytest.mark.asyncio
async def test_selfserve_rate_limit_bloqueia_quarta_arena_no_mesmo_dia(client):
    ctx = usuario_comum_ctx()
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=3)):
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Quarta Arena", "slug": "quarta-arena"})

    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_selfserve_colisao_de_nome_retorna_409(client):
    ctx = usuario_comum_ctx()
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    existentes = [{"nome": "Canal3", "slug": "canal3"}]
    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=0)), \
         patch("repositories.arena.listar_nome_slug", AsyncMock(return_value=existentes)):
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Canal3", "slug": "canal3-novo"})

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_selfserve_heuristica_de_risco_nasce_draft(client):
    """Nome 'quase-igual' a uma arena existente (suspeito, não
    bloqueado) — nasce status='draft' em vez de 'published'."""
    ctx = usuario_comum_ctx()
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    existentes = [{"nome": "Turbo Clash", "slug": "turbo-clash"}]
    arena_draft = _arena(nome="Turbo Crash", slug="turbo-crash", status="draft")
    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=0)), \
         patch("repositories.arena.listar_nome_slug", AsyncMock(return_value=existentes)), \
         patch("repositories.arena.criar", AsyncMock(return_value=arena_draft)) as criar_mock, \
         patch("repositories.membership.criar", AsyncMock(return_value={})), \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)), \
         patch("repositories.arena.transferir_titularidade", AsyncMock(return_value=arena_draft)):

        resp = await client.post("/api/admin/arenas",
            json={"nome": "Turbo Crash", "slug": "turbo-crash"})

    assert resp.status_code == 201
    # 2º argumento posicional após pool é status (kwarg) — confirma draft
    kwargs = criar_mock.call_args.kwargs
    assert kwargs.get("status") == "draft"


@pytest.mark.asyncio
async def test_selfserve_segunda_arena_no_mesmo_dia_nasce_draft_mesmo_com_nome_normal(client):
    """Velocidade anômala (2ª+ arena da mesma conta em 24h) já é sinal
    o bastante — nasce draft mesmo sem colisão/quase-igual de nome."""
    ctx = usuario_comum_ctx()
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena_draft = _arena(nome="Segunda Arena do Dia", slug="segunda-arena-do-dia", status="draft")
    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=1)), \
         patch("repositories.arena.listar_nome_slug", AsyncMock(return_value=[])), \
         patch("repositories.arena.criar", AsyncMock(return_value=arena_draft)) as criar_mock, \
         patch("repositories.membership.criar", AsyncMock(return_value={})), \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)), \
         patch("repositories.arena.transferir_titularidade", AsyncMock(return_value=arena_draft)):

        resp = await client.post("/api/admin/arenas",
            json={"nome": "Segunda Arena do Dia", "slug": "segunda-arena-do-dia"})

    assert resp.status_code == 201
    assert criar_mock.call_args.kwargs.get("status") == "draft"


@pytest.mark.asyncio
async def test_selfserve_caso_normal_nasce_published(client):
    ctx = usuario_comum_ctx()
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena = _arena(status="published")
    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=0)), \
         patch("repositories.arena.listar_nome_slug", AsyncMock(return_value=[])), \
         patch("repositories.arena.criar", AsyncMock(return_value=arena)) as criar_mock, \
         patch("repositories.membership.criar", AsyncMock(return_value={})), \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)), \
         patch("repositories.arena.transferir_titularidade", AsyncMock(return_value=arena)):

        resp = await client.post("/api/admin/arenas",
            json={"nome": "Liga dos Amigos", "slug": "liga-dos-amigos"})

    assert resp.status_code == 201
    assert criar_mock.call_args.kwargs.get("status") == "published"


@pytest.mark.asyncio
async def test_selfserve_logo_url_hostil_rejeitada(client):
    ctx = usuario_comum_ctx()
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=0)):
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Arena X", "slug": "arena-x", "logo_url": "javascript:alert(1)"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_super_isento_de_rate_limit_nao_chama_contagem(client):
    """Caminho super não passa pela admissão B.2-B.4 — não deve nem
    chamar a contagem de rate limit (G.4)."""
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena = _arena(status="published")
    with patch("repositories.arena.criar", AsyncMock(return_value=arena)), \
         patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=0)) as contagem_mock:
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Liga dos Amigos", "slug": "liga-dos-amigos"})

    assert resp.status_code == 201
    contagem_mock.assert_not_called()


@pytest.mark.asyncio
async def test_arena_draft_nunca_aparece_em_listagem_publica():
    """Consulta usada pela home institucional pra descoberta
    (com-event-ativo) exige status='published' explicitamente — arena
    sinalizada por B.4 não pode vazar em nenhuma superfície pública."""
    import repositories.arena as arena_repo
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])

    await arena_repo.listar_com_event_ativo(pool)

    sql = " ".join(pool.fetch.call_args[0][0].split())
    assert "status = 'published'" in sql


@pytest.mark.asyncio
async def test_eventos_abertos_exige_arena_published():
    import repositories.event as event_repo
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])

    await event_repo.listar_abertos(pool)

    sql = " ".join(pool.fetch.call_args[0][0].split())
    assert "visibility = 'open'" in sql
    assert "m.status = 'published'" in sql
