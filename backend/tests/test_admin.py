import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin

ADMIN_SECRET = "test-secret-123"
AUTH_HEADER  = {"Authorization": f"Bearer {ADMIN_SECRET}"}


def make_uuid():
    return str(uuid.uuid4())


def make_entrada(nick="PLAYER1", pontuacao=50000, jogo_id=None,
                 no_ranking=True, pendente=False,
                 foto_url="https://cdn.example.com/foto.jpg"):
    return {
        "id": make_uuid(), "jogo_id": jogo_id or make_uuid(),
        "nick": nick, "nick_norm": nick.lower().strip(),
        "pontuacao": pontuacao, "foto_url": foto_url,
        "no_ranking": no_ranking, "superado": False, "pendente": pendente,
        "ip_hash": "abc123", "criado_em": "2024-01-01T00:00:00Z",
        "moderado_em": None, "moderado_por": None,
    }


def make_jogo():
    return {"id": make_uuid(), "slug": "pac-man", "nome": "Pac-Man",
            "score_max": 999990, "ativo": True}


def _pool_com_slug(slug="pac-man"):
    """Pool mock que responde o slug do jogo quando consultado."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"slug": slug})
    pool.fetch    = AsyncMock(return_value=[])
    return pool


@pytest.fixture(autouse=True)
def override_auth():
    """Substitui autenticação via dependency_overrides."""
    app.dependency_overrides[require_admin] = lambda: ADMIN_SECRET
    yield
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(autouse=True)
def clear_pool_override():
    """Garante limpeza do override do pool após cada teste."""
    yield
    app.dependency_overrides.pop(get_pool, None)


# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sem_token_retorna_401(client):
    """Sem override de auth, deve retornar 401."""
    app.dependency_overrides.pop(require_admin, None)
    resp = await client.get("/api/admin/feed")
    assert resp.status_code == 401
    # Restaura para os outros testes
    app.dependency_overrides[require_admin] = lambda: ADMIN_SECRET


@pytest.mark.asyncio
async def test_token_errado_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)
    resp = await client.get("/api/admin/feed",
                            headers={"Authorization": "Bearer errado"})
    assert resp.status_code == 401
    app.dependency_overrides[require_admin] = lambda: ADMIN_SECRET


@pytest.mark.asyncio
async def test_token_correto_retorna_200(client):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.entrada.listar_feed_admin", AsyncMock(return_value=[])):
        resp = await client.get("/api/admin/feed", headers=AUTH_HEADER)
    assert resp.status_code == 200


# ── Moderação ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocultar_entrada(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, no_ranking=True)
    entrada_ocultada = {**entrada, "no_ranking": False}

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entrada.atualizar_visibilidade",
               AsyncMock(return_value=entrada_ocultada)), \
         patch("routers.admin.broker.publish", AsyncMock()):
        resp = await client.patch(
            f"/api/admin/entradas/{entrada['id']}",
            json={"no_ranking": False}, headers=AUTH_HEADER)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ocultar_entrada_inexistente_retorna_404(client):
    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entrada.atualizar_visibilidade", AsyncMock(return_value=None)):
        resp = await client.patch(
            f"/api/admin/entradas/{make_uuid()}",
            json={"no_ranking": False}, headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_aprovar_pendente(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, pendente=True, no_ranking=False)
    entrada_aprovada = {**entrada, "pendente": False, "no_ranking": True}

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entrada.resolver_pendente",
               AsyncMock(return_value=entrada_aprovada)), \
         patch("routers.admin.broker.publish", AsyncMock()):
        resp = await client.patch(
            f"/api/admin/entradas/{entrada['id']}/pendente",
            json={"aprovar": True}, headers=AUTH_HEADER)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_aprovar_pendente_publica_sse(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, pendente=True, no_ranking=False)
    entrada_aprovada = {**entrada, "pendente": False, "no_ranking": True}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entrada.resolver_pendente",
               AsyncMock(return_value=entrada_aprovada)), \
         patch("routers.admin.broker.publish", broker_mock):
        await client.patch(
            f"/api/admin/entradas/{entrada['id']}/pendente",
            json={"aprovar": True}, headers=AUTH_HEADER)

    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "novo_registro"


@pytest.mark.asyncio
async def test_rejeitar_pendente_nao_publica_sse(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, pendente=True, no_ranking=False)
    entrada_rejeitada = {**entrada, "pendente": False, "no_ranking": False}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entrada.resolver_pendente",
               AsyncMock(return_value=entrada_rejeitada)), \
         patch("routers.admin.broker.publish", broker_mock):
        await client.patch(
            f"/api/admin/entradas/{entrada['id']}/pendente",
            json={"aprovar": False}, headers=AUTH_HEADER)

    broker_mock.assert_not_called()


# ── Jogos ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_jogo(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.jogo.criar", AsyncMock(return_value=make_jogo())):
        resp = await client.post("/api/admin/jogos",
                                 json={"nome": "Pac-Man", "slug": "pac-man"},
                                 headers=AUTH_HEADER)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_criar_jogo_slug_duplicado_retorna_409(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.jogo.criar",
               AsyncMock(side_effect=Exception("unique constraint"))):
        resp = await client.post("/api/admin/jogos",
                                 json={"nome": "Pac-Man", "slug": "pac-man"},
                                 headers=AUTH_HEADER)
    assert resp.status_code == 409


# ── Config ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_config(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.evento_config.listar", AsyncMock(return_value={
        "rate_limit": {"valor": "10", "descricao": "limite"},
    })):
        resp = await client.get("/api/admin/config", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "rate_limit" in resp.json()


@pytest.mark.asyncio
async def test_atualizar_config(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.evento_config.atualizar", AsyncMock(return_value={
        "chave": "rate_limit", "valor": "20", "descricao": "limite"
    })):
        resp = await client.patch("/api/admin/config/rate_limit",
                                  json={"valor": "20"}, headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["valor"] == "20"


# ── Manutenção — limpar ranking ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_limpar_ranking_sem_confirmar_retorna_400(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"permanente": False, "confirmar": "errado"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_limpar_ranking_soft_delete(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=5)
    pool.execute  = AsyncMock(return_value="UPDATE 5")
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"permanente": False, "confirmar": "CONFIRMAR"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["permanente"] is False
    assert data["total_afetadas"] == 5


@pytest.mark.asyncio
async def test_limpar_ranking_permanente(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=3)
    pool.execute  = AsyncMock(return_value="DELETE 3")
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"permanente": True, "confirmar": "CONFIRMAR"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["permanente"] is True


@pytest.mark.asyncio
async def test_limpar_ranking_por_jogo(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=2)
    pool.execute  = AsyncMock(return_value="UPDATE 2")
    app.dependency_overrides[get_pool] = lambda: pool
    jogo_id = make_uuid()

    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"jogo_id": jogo_id, "permanente": False, "confirmar": "CONFIRMAR"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["total_afetadas"] == 2


@pytest.mark.asyncio
async def test_restaurar_ranking(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=4)
    pool.execute  = AsyncMock(return_value="UPDATE 4")
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/manutencao/restaurar-ranking",
                             json={"confirmar": "CONFIRMAR"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["total_restauradas"] == 4


@pytest.mark.asyncio
async def test_restaurar_ranking_sem_confirmar_retorna_400(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/admin/manutencao/restaurar-ranking",
                             json={"confirmar": ""},
                             headers=AUTH_HEADER)
    assert resp.status_code == 400