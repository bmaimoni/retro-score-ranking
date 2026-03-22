import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid

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


@pytest.fixture(autouse=True)
def patch_auth():
    with patch("middleware.auth.get_settings") as m:
        m.return_value.admin_secret = ADMIN_SECRET
        yield


# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sem_token_retorna_401(client):
    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())):
        resp = await client.get("/api/admin/feed")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_errado_retorna_401(client):
    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())):
        resp = await client.get("/api/admin/feed",
                                headers={"Authorization": "Bearer errado"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_correto_retorna_200(client):
    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())), \
         patch("repositories.entrada.listar_feed_admin", AsyncMock(return_value=[])):
        resp = await client.get("/api/admin/feed", headers=AUTH_HEADER)
    assert resp.status_code == 200


# ── Moderação ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocultar_entrada(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, no_ranking=True)
    entrada_ocultada = {**entrada, "no_ranking": False}

    # Pool com fetchrow respondendo o slug do jogo
    pool_mock = AsyncMock()
    pool_mock.fetchrow = AsyncMock(return_value={"slug": "pac-man"})

    with patch("routers.admin.get_pool", AsyncMock(return_value=pool_mock)), \
         patch("repositories.entrada.atualizar_visibilidade",
               AsyncMock(return_value=entrada_ocultada)), \
         patch("routers.admin.broker.publish", AsyncMock()):
        resp = await client.patch(
            f"/api/admin/entradas/{entrada['id']}",
            json={"no_ranking": False},
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ocultar_entrada_inexistente_retorna_404(client):
    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())), \
         patch("repositories.entrada.atualizar_visibilidade", AsyncMock(return_value=None)):
        resp = await client.patch(
            f"/api/admin/entradas/{make_uuid()}",
            json={"no_ranking": False},
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_aprovar_pendente(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, pendente=True, no_ranking=False)
    entrada_aprovada = {**entrada, "pendente": False, "no_ranking": True}

    pool_mock = AsyncMock()
    pool_mock.fetchrow = AsyncMock(return_value={"slug": "pac-man"})

    with patch("routers.admin.get_pool", AsyncMock(return_value=pool_mock)), \
         patch("repositories.entrada.resolver_pendente",
               AsyncMock(return_value=entrada_aprovada)), \
         patch("routers.admin.broker.publish", AsyncMock()):
        resp = await client.patch(
            f"/api/admin/entradas/{entrada['id']}/pendente",
            json={"aprovar": True},
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_aprovar_pendente_publica_sse(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, pendente=True, no_ranking=False)
    entrada_aprovada = {**entrada, "pendente": False, "no_ranking": True}

    pool_mock = AsyncMock()
    pool_mock.fetchrow = AsyncMock(return_value={"slug": "pac-man"})
    broker_mock = AsyncMock()

    with patch("routers.admin.get_pool", AsyncMock(return_value=pool_mock)), \
         patch("repositories.entrada.resolver_pendente",
               AsyncMock(return_value=entrada_aprovada)), \
         patch("routers.admin.broker.publish", broker_mock):
        await client.patch(
            f"/api/admin/entradas/{entrada['id']}/pendente",
            json={"aprovar": True},
            headers=AUTH_HEADER,
        )

    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "novo_registro"


@pytest.mark.asyncio
async def test_rejeitar_pendente_nao_publica_sse(client):
    jogo_id = make_uuid()
    entrada = make_entrada(jogo_id=jogo_id, pendente=True, no_ranking=False)
    entrada_rejeitada = {**entrada, "pendente": False, "no_ranking": False}
    broker_mock = AsyncMock()

    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())), \
         patch("repositories.entrada.resolver_pendente",
               AsyncMock(return_value=entrada_rejeitada)), \
         patch("routers.admin.broker.publish", broker_mock):
        await client.patch(
            f"/api/admin/entradas/{entrada['id']}/pendente",
            json={"aprovar": False},
            headers=AUTH_HEADER,
        )

    broker_mock.assert_not_called()


# ── Jogos ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_jogo(client):
    jogo = make_jogo()
    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())), \
         patch("repositories.jogo.criar", AsyncMock(return_value=jogo)):
        resp = await client.post(
            "/api/admin/jogos",
            json={"nome": "Pac-Man", "slug": "pac-man"},
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_criar_jogo_slug_duplicado_retorna_409(client):
    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())), \
         patch("repositories.jogo.criar",
               AsyncMock(side_effect=Exception("unique constraint"))):
        resp = await client.post(
            "/api/admin/jogos",
            json={"nome": "Pac-Man", "slug": "pac-man"},
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 409


# ── Config ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_config(client):
    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())), \
         patch("repositories.evento_config.listar", AsyncMock(return_value={
             "rate_limit": {"valor": "10", "descricao": "limite"},
         })):
        resp = await client.get("/api/admin/config", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "rate_limit" in resp.json()


@pytest.mark.asyncio
async def test_atualizar_config(client):
    with patch("routers.admin.get_pool", AsyncMock(return_value=AsyncMock())), \
         patch("repositories.evento_config.atualizar", AsyncMock(return_value={
             "chave": "rate_limit", "valor": "20", "descricao": "limite"
         })):
        resp = await client.patch(
            "/api/admin/config/rate_limit",
            json={"valor": "20"},
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 200
    assert resp.json()["valor"] == "20"