"""
Testes unitários do endpoint POST /api/e/{slug}/upload.
Cobrem: validação de arquivo, campos obrigatórios e regras de negócio.

Endpoint escopado por evento desde EVENTOS_SPEC.md — o antigo
POST /api/upload (genérico, sem evento) foi removido.
"""
import io
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool

JOGO_ID   = "550e8400-e29b-41d4-a716-446655440000"
EVENTO_SLUG = "canal3expo"
URL       = f"/api/e/{EVENTO_SLUG}/upload"
FOTO_URL  = "https://cdn.example.com/foto.jpg"


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


def _evento():
    """Evento aberto: publico=true e dentro da janela de envio."""
    return {
        "id": str(uuid.uuid4()), "nome": "Canal3 Expo", "slug": EVENTO_SLUG,
        "ativo": True, "publico": True,
        "data_inicio": datetime.now(timezone.utc) - timedelta(days=1),
        "data_fim":    datetime.now(timezone.utc) + timedelta(days=1),
    }


def _entrada(pendente=False, foto_url=FOTO_URL, nome=None):
    return {
        "id": str(uuid.uuid4()), "jogo_id": JOGO_ID,
        "nick": "P1", "nome": nome, "pontuacao": 5000,
        "foto_url": foto_url,
        "no_ranking": not pendente, "pendente": pendente,
        "superado": False, "criado_em": "2024-01-01",
        "mensagem": "Você está no ranking!" if not pendente else "Em análise.",
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


def _setup(pendente=False, foto_url=FOTO_URL, nome=None):
    entry = _entrada(pendente=pendente, foto_url=foto_url, nome=nome)
    pool  = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool
    return entry, pool


def _patches(entry, publish_mock=None, inserir_mock=None):
    """Contexto padrão de patches para o fluxo de upload evento-scoped."""
    return [
        patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())),
        patch("routers.evento_publico.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)),
        patch("routers.evento_publico.rl.checar_rate_limit",  AsyncMock(return_value=False)),
        patch("routers.evento_publico.score_svc.validar_score", AsyncMock(return_value=None)),
        patch("routers.evento_publico.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)),
        patch("routers.evento_publico.broker.publish",          publish_mock or AsyncMock()),
        patch("routers.evento_publico.entrada_repo.inserir",    inserir_mock or AsyncMock(return_value=entry)),
        patch("routers.evento_publico._slug_from_id",           AsyncMock(return_value="pac-man")),
    ]


def _apply(patches):
    from contextlib import ExitStack
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


# ── Validação de evento (novidade do endpoint escopado) ───────────────────────

@pytest.mark.asyncio
async def test_rejeita_evento_inexistente(client):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    app.dependency_overrides[get_pool] = lambda: pool
    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.post(URL,
            data={"nick": "X", "pontuacao": "1", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 404


# ── Validação de arquivo ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejeita_acima_de_5mb(client):
    grande = b"x" * (5 * 1024 * 1024 + 1)
    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())):
        resp = await client.post(URL,
            data={"nick": "X", "pontuacao": "1", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(grande), "image/jpeg"))])
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_rejeita_pdf_com_extensao_jpg(client):
    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())):
        resp = await client.post(URL,
            data={"nick": "X", "pontuacao": "1", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_pdf_bytes()), "image/jpeg"))])
    assert resp.status_code == 422
    assert "Formato inválido" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_aceita_jpeg_valido(client):
    entry, _ = _setup()
    with _apply(_patches(entry)):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_aceita_png_valido(client):
    entry, _ = _setup()
    with _apply(_patches(entry)):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.png", io.BytesIO(make_png_bytes()), "image/png"))])
    assert resp.status_code == 201


# ── Campos obrigatórios ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejeita_sem_nick(client):
    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())):
        resp = await client.post(URL,
            data={"pontuacao": "1000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejeita_score_zero(client):
    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())):
        resp = await client.post(URL,
            data={"nick": "X", "pontuacao": "0", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejeita_score_negativo(client):
    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())):
        resp = await client.post(URL,
            data={"nick": "X", "pontuacao": "-100", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 422


# ── Regras de negócio ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sem_foto_entra_como_pendente(client):
    entry, _ = _setup(pendente=True, foto_url=None)
    patches = _patches(entry)
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID})
    assert resp.status_code == 201
    data = resp.json()
    assert data["pendente"] is True
    assert "análise" in data["mensagem"]


@pytest.mark.asyncio
async def test_rate_limit_entra_como_pendente(client):
    entry, _ = _setup(pendente=True)
    patches = [
        patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())),
        patch("routers.evento_publico.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)),
        patch("routers.evento_publico.rl.checar_rate_limit",  AsyncMock(return_value=True)),
        patch("routers.evento_publico.score_svc.validar_score", AsyncMock(return_value=None)),
        patch("routers.evento_publico.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)),
        patch("routers.evento_publico.broker.publish",          AsyncMock()),
        patch("routers.evento_publico.entrada_repo.inserir",    AsyncMock(return_value=entry)),
        patch("routers.evento_publico._slug_from_id",           AsyncMock(return_value="pac-man")),
    ]
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "Spam", "pontuacao": "1000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 201
    assert resp.json()["pendente"] is True


@pytest.mark.asyncio
async def test_pendente_nao_publica_sse(client):
    entry, _ = _setup(pendente=True)
    broker_mock = AsyncMock()
    patches = [
        patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())),
        patch("routers.evento_publico.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)),
        patch("routers.evento_publico.rl.checar_rate_limit",  AsyncMock(return_value=True)),
        patch("routers.evento_publico.score_svc.validar_score", AsyncMock(return_value=None)),
        patch("routers.evento_publico.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)),
        patch("routers.evento_publico.broker.publish",          broker_mock),
        patch("routers.evento_publico.entrada_repo.inserir",    AsyncMock(return_value=entry)),
        patch("routers.evento_publico._slug_from_id",           AsyncMock(return_value="pac-man")),
    ]
    with _apply(patches):
        await client.post(URL,
            data={"nick": "P", "pontuacao": "1", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    broker_mock.assert_not_called()


@pytest.mark.asyncio
async def test_upload_normal_publica_sse(client):
    entry, _ = _setup()
    broker_mock = AsyncMock()
    with _apply(_patches(entry, publish_mock=broker_mock)):
        await client.post(URL,
            data={"nick": "P", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "novo_registro"


@pytest.mark.asyncio
async def test_retorno_contem_mensagem(client):
    entry, _ = _setup()
    with _apply(_patches(entry)):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert "mensagem" in resp.json()
    assert "ranking" in resp.json()["mensagem"].lower()


@pytest.mark.asyncio
async def test_evento_id_gravado_na_entrada(client):
    """A entrada gravada deve sempre incluir o evento_id do evento da URL."""
    entry, _ = _setup()
    inserir_mock = AsyncMock(return_value=entry)
    evento = _evento()
    patches = [
        patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=evento)),
        patch("routers.evento_publico.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)),
        patch("routers.evento_publico.rl.checar_rate_limit",  AsyncMock(return_value=False)),
        patch("routers.evento_publico.score_svc.validar_score", AsyncMock(return_value=None)),
        patch("routers.evento_publico.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)),
        patch("routers.evento_publico.broker.publish",          AsyncMock()),
        patch("routers.evento_publico.entrada_repo.inserir",    inserir_mock),
        patch("routers.evento_publico._slug_from_id",           AsyncMock(return_value="pac-man")),
    ]
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 201
    dados_inseridos = inserir_mock.call_args[0][1]
    assert dados_inseridos.get("evento_id") == evento["id"]


# ── Campo nome ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nome_enviado_e_salvo(client):
    """Campo nome deve ser repassado para o repositório."""
    entry, _ = _setup(nome="Maria Silva")
    inserir_mock = AsyncMock(return_value=entry)
    with _apply(_patches(entry, inserir_mock=inserir_mock)):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID, "nome": "Maria Silva"},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 201
    dados_inseridos = inserir_mock.call_args[0][1]
    assert dados_inseridos.get("nome") == "Maria Silva"


@pytest.mark.asyncio
async def test_nome_opcional_sem_nome(client):
    """Upload sem nome deve funcionar normalmente."""
    entry, _ = _setup()
    with _apply(_patches(entry)):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])
    assert resp.status_code == 201
