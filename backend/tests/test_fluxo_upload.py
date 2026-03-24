"""
Testes de integração do fluxo completo de upload.
"""
import io
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool

JOGO_ID = "550e8400-e29b-41d4-a716-446655440000"
URL     = "/api/upload"


def make_uuid():
    return str(uuid.uuid4())


def make_jpeg_bytes():
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xd9")


def _entrada(nick="P1", pontuacao=5000, pendente=False,
             no_ranking=True, foto_url="https://cdn/f.jpg"):
    return {
        "id": make_uuid(), "jogo_id": JOGO_ID, "nick": nick,
        "pontuacao": pontuacao, "foto_url": foto_url,
        "no_ranking": no_ranking, "pendente": pendente,
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


@pytest.mark.asyncio
async def test_upload_com_foto_entra_direto_no_ranking(client):
    entry = _entrada()
    pool  = _make_pool(entry)
    broker = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.upload.storage.upload_foto",  AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit", AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",        broker), \
         patch("routers.upload.evento_repo.buscar_ativo_mais_recente", AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir",  AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",         AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201
    assert resp.json()["pendente"] is False
    broker.assert_called_once()


@pytest.mark.asyncio
async def test_upload_sem_foto_vai_para_moderacao(client):
    entry  = _entrada(pendente=True, no_ranking=False, foto_url=None)
    pool   = _make_pool(entry)
    broker = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          broker), \
         patch("routers.upload.evento_repo.buscar_ativo_mais_recente", AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID})

    assert resp.status_code == 201
    assert resp.json()["pendente"] is True
    broker.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_ativado_vai_para_moderacao(client):
    entry  = _entrada(pendente=True, no_ranking=False)
    pool   = _make_pool(entry)
    broker = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=True)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          broker), \
         patch("routers.upload.evento_repo.buscar_ativo_mais_recente", AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201
    assert resp.json()["pendente"] is True
    broker.assert_not_called()


@pytest.mark.asyncio
async def test_nick_repetido_marca_anterior_como_superado(client):
    entry      = _entrada()
    pool       = _make_pool(entry)
    marcar_mock = AsyncMock(return_value="uuid-anterior")

    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", marcar_mock), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.evento_repo.buscar_ativo_mais_recente", AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):
        await client.post(URL,
            data={"nick": "P1", "pontuacao": "9999", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    marcar_mock.assert_called_once()


@pytest.mark.asyncio
async def test_score_acima_do_maximo_retorna_422(client):
    from fastapi import HTTPException
    pool = _make_pool(_entrada())

    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.upload.storage.upload_foto",  AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit", AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score",
               AsyncMock(side_effect=HTTPException(422, "Pontuacao excede o maximo"))):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "9999999", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 422


# ── Campo nome ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_nome_salvo_no_banco(client):
    """Campo nome deve ser passado ao inserir entrada."""
    entry = _entrada()
    entry["nome"] = "Carlos Lima"
    pool  = _make_pool(entry)
    inserir_mock = AsyncMock(return_value=entry)

    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.evento_repo.buscar_ativo_mais_recente", AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir",    inserir_mock), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID, "nome": "Carlos Lima"},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201
    dados = inserir_mock.call_args[0][1]
    assert dados.get("nome") == "Carlos Lima"


@pytest.mark.asyncio
async def test_upload_sem_nome_funciona(client):
    """nome é opcional — ausência não deve causar erro."""
    entry = _entrada()
    pool  = _make_pool(entry)

    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.upload.storage.upload_foto",   AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",          AsyncMock()), \
         patch("routers.upload.evento_repo.buscar_ativo_mais_recente", AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir",    AsyncMock(return_value=entry)), \
         patch("routers.upload._slug_from_id",           AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):
        resp = await client.post(URL,
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201