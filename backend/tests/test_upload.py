"""
Testes unitários do endpoint POST /api/upload.
Cobrem: validação de arquivo, campos obrigatórios e regras de negócio.
"""
import io
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool

JOGO_ID  = "550e8400-e29b-41d4-a716-446655440000"
URL      = "/api/upload"
FOTO_URL = "https://cdn.example.com/foto.jpg"


def make_jpeg_bytes():
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xd9")

def make_png_bytes():
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82")

def make_pdf_bytes():
    return b"%PDF-1.4 fake content that is definitely not an image"


def _entrada(pendente=False, foto_url=FOTO_URL):
    return {
        "id": str(uuid.uuid4()), "jogo_id": JOGO_ID,
        "nick": "P1", "pontuacao": 5000,
        "foto_url": foto_url,
        "no_ranking": not pendente, "pendente": pendente,
        "superado": False, "criado_em": "2024-01-01",
    }


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


class _FakeConn:
    def __init__(self, entry):
        self.fetchrow    = AsyncMock(return_value=entry)
        self.execute     = AsyncMock(return_value="UPDATE 1")
        self.transaction = MagicMock(return_value=_FakeTxn())

    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


def _make_pool(entry):
    conn = _FakeConn(entry)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=0)
    pool.acquire  = MagicMock(return_value=conn)
    return pool


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


def _setup(pendente=False, foto_url=FOTO_URL):
    """Configura dependency_overrides e patches para um upload padrão."""
    entry = _entrada(pendente=pendente, foto_url=foto_url)
    pool  = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool
    return entry, pool


# ── Validação de arquivo ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejeita_acima_de_5mb(client):
    grande = b"x" * (5 * 1024 * 1024 + 1)
    resp = await client.post(URL,
        data={"nick": "X", "pontuacao": "1", "jogo_id": JOGO_ID},
        files=[("foto", ("f.jpg", io.BytesIO(grande), "image/jpeg"))])
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_rejeita_pdf_com_extensao_jpg(client):
    resp = await client.post(URL,
        data={"nick": "X", "pontuacao": "1", "jogo_id": JOGO_ID},
        files=[("foto", ("f.jpg", io.BytesIO(make_pdf_bytes()), "image/jpeg"))])
    assert resp.status_code == 422
    assert "Formato inválido" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_aceita_jpeg_valido(client):
    entry, _ = _setup()
    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_aceita_png_valido(client):
    entry, _ = _setup()
    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.png", io.BytesIO(make_png_bytes()), "image/png"))])
    assert resp.status_code == 201


# ── Campos obrigatórios ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejeita_sem_nick(client):
    resp = await client.post(URL,
        data={"pontuacao": "1000", "jogo_id": JOGO_ID},
        files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejeita_score_zero(client):
    resp = await client.post(URL,
        data={"nick": "X", "pontuacao": "0", "jogo_id": JOGO_ID},
        files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejeita_score_negativo(client):
    resp = await client.post(URL,
        data={"nick": "X", "pontuacao": "-100", "jogo_id": JOGO_ID},
        files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 422


# ── Regras de negócio ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sem_foto_entra_como_pendente(client):
    entry, _ = _setup(pendente=True, foto_url=None)
    with patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID})

    assert resp.status_code == 201
    data = resp.json()
    assert data["pendente"] is True
    assert "análise" in data["mensagem"]


@pytest.mark.asyncio
async def test_rate_limit_entra_como_pendente(client):
    entry, _ = _setup(pendente=True)
    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=True)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")):
        resp = await client.post(URL,
            data={"nick": "Spam", "pontuacao": "1000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201
    assert resp.json()["pendente"] is True


@pytest.mark.asyncio
async def test_pendente_nao_publica_sse(client):
    entry, _ = _setup(pendente=True)
    broker_mock = AsyncMock()

    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=True)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          broker_mock), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")):
        await client.post(URL,
            data={"nick": "P", "pontuacao": "1", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    broker_mock.assert_not_called()


@pytest.mark.asyncio
async def test_upload_normal_publica_sse(client):
    entry, _ = _setup()
    broker_mock = AsyncMock()

    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          broker_mock), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):
        await client.post(URL,
            data={"nick": "P", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "novo_registro"


@pytest.mark.asyncio
async def test_retorno_contem_mensagem(client):
    """Campo mensagem deve estar presente e variar conforme pendente."""
    entry, _ = _setup()
    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert "mensagem" in resp.json()
    assert "ranking" in resp.json()["mensagem"].lower()