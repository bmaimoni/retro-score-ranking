"""
Testes do repositório e endpoints de eventos.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin

ADMIN_SECRET = "test-secret"
AUTH_HEADER  = {"Authorization": f"Bearer {ADMIN_SECRET}"}


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


class _FakeConn:
    def __init__(self, entry=None):
        self.fetchrow    = AsyncMock(return_value=entry)
        self.execute     = AsyncMock(return_value="UPDATE 1")
        self.transaction = MagicMock(return_value=_FakeTxn())

    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


def _make_pool(entry=None):
    conn = _FakeConn(entry)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=0)
    pool.fetch    = AsyncMock(return_value=[])
    pool.acquire  = MagicMock(return_value=conn)
    return pool


def make_uuid():
    return str(uuid.uuid4())


def _evento(ativo=True, nome="Canal3 Expo 2024", slug="canal3-expo-2024"):
    return {
        "id": make_uuid(), "nome": nome, "slug": slug,
        "ativo": ativo, "data_inicio": "2024-11-02T00:00:00",
        "data_fim": None, "criado_em": "2024-01-01T00:00:00",
    }


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides[require_admin] = lambda: ADMIN_SECRET
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Listar ativos (público) ───────────────────────────────────

@pytest.mark.asyncio
async def test_listar_ativos_retorna_somente_ativos(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.listar_ativos", AsyncMock(return_value=[_evento(ativo=True)])):
        resp = await client.get("/api/admin/eventos/ativos")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["ativo"] is True


@pytest.mark.asyncio
async def test_listar_ativos_vazio(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.listar_ativos", AsyncMock(return_value=[])):
        resp = await client.get("/api/admin/eventos/ativos")

    assert resp.status_code == 200
    assert resp.json() == []


# ── Criar evento ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_evento(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.criar", AsyncMock(return_value=_evento())):
        resp = await client.post("/api/admin/eventos",
            json={"nome": "Canal3 Expo 2024", "slug": "canal3-expo-2024"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["slug"] == "canal3-expo-2024"


@pytest.mark.asyncio
async def test_criar_evento_sem_auth_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)  # remove override p/ testar auth real
    resp = await client.post("/api/admin/eventos",
        json={"nome": "Teste", "slug": "teste"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_criar_evento_slug_duplicado_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.criar",
               AsyncMock(side_effect=Exception("unique constraint"))):
        resp = await client.post("/api/admin/eventos",
            json={"nome": "Dup", "slug": "dup"},
            headers=AUTH_HEADER)

    assert resp.status_code == 409


# ── Atualizar evento ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_desativar_evento(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.atualizar", AsyncMock(return_value=_evento(ativo=False))):
        resp = await client.patch(f"/api/admin/eventos/{make_uuid()}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_evento_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.atualizar", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/eventos/{make_uuid()}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


# ── Upload associa evento_id ──────────────────────────────────

@pytest.mark.asyncio
async def test_upload_associa_evento_ativo(client):
    """Upload deve buscar evento ativo e incluir evento_id na entrada."""
    import io
    evento  = _evento()
    jogo_id = make_uuid()
    entrada = {
        "id": make_uuid(), "jogo_id": jogo_id, "nick": "P1", "nome": None,
        "pontuacao": 5000, "foto_url": "https://cdn/f.jpg",
        "no_ranking": True, "pendente": False,
        "evento_id": evento["id"], "criado_em": "2024-01-01",
    }
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = _make_pool(entrada)
    app.dependency_overrides[get_pool] = lambda: pool
    inserir_mock = AsyncMock(return_value=entrada)

    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.entrada_repo.inserir",    inserir_mock), \
         patch("routers.upload.evento_repo.buscar_ativo_mais_recente", AsyncMock(return_value=evento)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="megamania")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "megamania"})):
        resp = await client.post("/api/upload",
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": jogo_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 201
    dados = inserir_mock.call_args[0][1]
    assert dados.get("evento_id") == evento["id"]


@pytest.mark.asyncio
async def test_upload_sem_evento_ativo_evento_id_none(client):
    """Sem evento ativo, evento_id deve ser None — upload não é bloqueado."""
    import io
    jogo_id = make_uuid()
    entrada = {
        "id": make_uuid(), "jogo_id": jogo_id, "nick": "P1", "nome": None,
        "pontuacao": 5000, "foto_url": "https://cdn/f.jpg",
        "no_ranking": True, "pendente": False,
        "evento_id": None, "criado_em": "2024-01-01",
    }
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = _make_pool(entrada)
    app.dependency_overrides[get_pool] = lambda: pool
    inserir_mock = AsyncMock(return_value=entrada)

    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.entrada_repo.inserir",    inserir_mock), \
         patch("routers.upload.evento_repo.buscar_ativo_mais_recente", AsyncMock(return_value=None)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="megamania")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "megamania"})):
        resp = await client.post("/api/upload",
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": jogo_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 201
    dados = inserir_mock.call_args[0][1]
    assert dados.get("evento_id") is None