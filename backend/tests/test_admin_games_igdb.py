"""
Testes de GET /api/admin/games/buscar-igdb e do caminho igdb_id de
POST /api/admin/games — Fase 9 + docs/CATALOGO_JOGOS_SPEC.md Fase 5.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext
import services.igdb as igdb

SUPER_CTX = AdminContext(identificador="admin", user_id=None, super=True)


def make_uuid():
    return str(uuid.uuid4())


def make_game(**overrides):
    base = {
        "id": make_uuid(), "slug": "street-fighter-ii", "nome": "Street Fighter II",
        "score_max": None, "ativo": True, "pendente_aprovacao": False,
        "criado_por": "admin", "criado_em": "2026-01-01", "igdb_id": 3186,
        "plataforma": "Arcade", "ano_lancamento": 1991, "capa_url": None, "gameplay_url": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── GET /api/admin/games/buscar-igdb ────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_igdb_sucesso(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resultados = [{"igdb_id": 3186, "nome": "Street Fighter II", "plataforma": "Arcade",
                    "ano_lancamento": 1991, "capa_url": None}]
    with patch("services.igdb.buscar", AsyncMock(return_value=resultados)):
        resp = await client.get("/api/admin/games/buscar-igdb?q=street+fighter")

    assert resp.status_code == 200
    assert resp.json() == resultados


@pytest.mark.asyncio
async def test_buscar_igdb_nao_configurado_retorna_503(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("services.igdb.buscar", AsyncMock(side_effect=igdb.IGDBNaoConfigurado())):
        resp = await client.get("/api/admin/games/buscar-igdb?q=street+fighter")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_buscar_igdb_indisponivel_retorna_503(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("services.igdb.buscar", AsyncMock(side_effect=igdb.IGDBIndisponivel("timeout"))):
        resp = await client.get("/api/admin/games/buscar-igdb?q=street+fighter")

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_buscar_igdb_sem_auth_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/admin/games/buscar-igdb?q=street+fighter")
    assert resp.status_code == 401


# ── POST /api/admin/games com igdb_id ───────────────────────────────

@pytest.mark.asyncio
async def test_criar_game_via_igdb_pula_aprovacao_mesmo_nao_super(client):
    """Admin não-super, igdb_id presente: nasce pendente_aprovacao=False
    direto — dedup estrutural já validou a entrada, sem fila de
    revisão (CATALOGO_JOGOS_SPEC.md 5.4)."""
    escopado = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": "m1", "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: escopado
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    criar_mock = AsyncMock(return_value=make_game(pendente_aprovacao=False))
    with patch("repositories.game.buscar_por_igdb_id", AsyncMock(return_value=None)), \
         patch("repositories.game.criar", criar_mock):
        resp = await client.post("/api/admin/games", json={
            "nome": "Street Fighter II", "slug": "street-fighter-ii", "igdb_id": 3186,
        })

    assert resp.status_code == 201
    assert resp.json()["pendente_aprovacao"] is False
    criar_mock.assert_called_once_with(
        pool, "Street Fighter II", "street-fighter-ii", None,
        pendente_aprovacao=False, criado_por="pessoa@x.com",
        plataforma=None, ano_lancamento=None, capa_url=None, gameplay_url=None,
        igdb_id=3186, generos=None, geracoes=None,
    )


@pytest.mark.asyncio
async def test_criar_game_via_igdb_repassa_generos_e_geracoes(client):
    """docs/CATALOGO_JOGOS_SPEC.md Fase 7 — generos/geracoes vindos da
    busca IGDB (frontend já resolveu via buscar-igdb) chegam até o
    repository, não só os campos que já existiam antes desta fase."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    criar_mock = AsyncMock(return_value=make_game())
    with patch("repositories.game.buscar_por_igdb_id", AsyncMock(return_value=None)), \
         patch("repositories.game.criar", criar_mock):
        resp = await client.post("/api/admin/games", json={
            "nome": "Street Fighter II", "slug": "street-fighter-ii",
            "igdb_id": 3186, "generos": ["Fighting"], "geracoes": [3, 4],
        })

    assert resp.status_code == 201
    criar_mock.assert_called_once_with(
        pool, "Street Fighter II", "street-fighter-ii", None,
        pendente_aprovacao=False, criado_por="admin",
        plataforma=None, ano_lancamento=None, capa_url=None, gameplay_url=None,
        igdb_id=3186, generos=["Fighting"], geracoes=[3, 4],
    )


@pytest.mark.asyncio
async def test_criar_game_via_igdb_id_repetido_reaproveita_existente(client):
    """igdb_id já cadastrado antes: reaproveita o game existente em vez
    de tentar criar duplicata (CATALOGO_JOGOS_SPEC.md 5.1)."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    existente = make_game()
    criar_mock = AsyncMock()  # não deve ser chamado
    with patch("repositories.game.buscar_por_igdb_id", AsyncMock(return_value=existente)), \
         patch("repositories.game.criar", criar_mock):
        resp = await client.post("/api/admin/games", json={
            "nome": "Street Fighter II", "slug": "street-fighter-ii-2", "igdb_id": 3186,
        })

    assert resp.status_code == 201
    assert resp.json()["id"] == existente["id"]
    criar_mock.assert_not_called()


@pytest.mark.asyncio
async def test_criar_game_via_igdb_id_vincula_a_event_id_informado(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    existente = make_game()
    with patch("repositories.game.buscar_por_igdb_id", AsyncMock(return_value=existente)), \
         patch("repositories.event_game.adicionar", AsyncMock()) as adicionar_mock:
        resp = await client.post("/api/admin/games", json={
            "nome": "Street Fighter II", "slug": "street-fighter-ii-2",
            "igdb_id": 3186, "event_id": "ev1",
        })

    assert resp.status_code == 201
    adicionar_mock.assert_called_once_with(pool, "ev1", str(existente["id"]))
