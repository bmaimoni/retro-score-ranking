import io
import uuid
import pytest
from unittest.mock import AsyncMock, patch
from conftest import make_jpeg_bytes, make_png_bytes, make_pdf_bytes

JOGO_ID  = "550e8400-e29b-41d4-a716-446655440000"
URL_API  = "/api/upload"
FOTO_URL = "https://cdn.example.com/foto.jpg"
ENTRADA  = {
    "id": str(uuid.uuid4()), "nick": "P1", "pontuacao": 5000,
    "foto_url": FOTO_URL, "no_ranking": True, "pendente": False,
    "criado_em": "2024-01-01",
}


def _patches(pendente=False, foto_url=FOTO_URL):
    entrada = {**ENTRADA, "no_ranking": not pendente, "pendente": pendente,
               "foto_url": foto_url}
    return [
        patch("routers.upload.get_pool",                          AsyncMock(return_value=AsyncMock())),
        patch("routers.upload.storage.upload_foto",               AsyncMock(return_value=foto_url)),
        patch("routers.upload.rl.checar_rate_limit",              AsyncMock(return_value=pendente)),
        patch("routers.upload.score_svc.validar_score",           AsyncMock(return_value=None)),
        patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)),
        patch("routers.upload.broker.publish",                    AsyncMock(return_value=None)),
        patch("routers.upload.entrada_repo.inserir",              AsyncMock(return_value=entrada)),
        patch("routers.upload._slug_from_id",                     AsyncMock(return_value="pac-man")),
        patch("routers.upload.jogo_repo.buscar_por_slug",         AsyncMock(return_value={"slug": "pac-man"})),
    ]


# ── Validação de arquivo ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejeita_acima_de_5mb(client):
    grande = b"x" * (5 * 1024 * 1024 + 1)
    resp = await client.post(URL_API, data={"nick":"X","pontuacao":"1","jogo_id":JOGO_ID},
                             files=[("foto",("f.jpg",io.BytesIO(grande),"image/jpeg"))])
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_rejeita_pdf_com_extensao_jpg(client):
    resp = await client.post(URL_API, data={"nick":"X","pontuacao":"1","jogo_id":JOGO_ID},
                             files=[("foto",("f.jpg",io.BytesIO(make_pdf_bytes()),"image/jpeg"))])
    assert resp.status_code == 422
    assert "Formato inválido" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_aceita_jpeg_valido(client):
    with (p := _patches())[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8]:
        resp = await client.post(URL_API,
            data={"nick":"P1","pontuacao":"5000","jogo_id":JOGO_ID},
            files=[("foto",("f.jpg",io.BytesIO(make_jpeg_bytes()),"image/jpeg"))])
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_aceita_png_valido(client):
    with (p := _patches())[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8]:
        resp = await client.post(URL_API,
            data={"nick":"P1","pontuacao":"5000","jogo_id":JOGO_ID},
            files=[("foto",("f.png",io.BytesIO(make_png_bytes()),"image/png"))])
    assert resp.status_code == 201


# ── Campos obrigatórios ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejeita_sem_nick(client):
    resp = await client.post(URL_API,
        data={"pontuacao":"1000","jogo_id":JOGO_ID},
        files=[("foto",("f.jpg",io.BytesIO(make_jpeg_bytes()),"image/jpeg"))])
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejeita_score_zero(client):
    resp = await client.post(URL_API,
        data={"nick":"X","pontuacao":"0","jogo_id":JOGO_ID},
        files=[("foto",("f.jpg",io.BytesIO(make_jpeg_bytes()),"image/jpeg"))])
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejeita_score_negativo(client):
    resp = await client.post(URL_API,
        data={"nick":"X","pontuacao":"-100","jogo_id":JOGO_ID},
        files=[("foto",("f.jpg",io.BytesIO(make_jpeg_bytes()),"image/jpeg"))])
    assert resp.status_code == 422


# ── Regras de negócio ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sem_foto_entra_como_pendente(client):
    entrada_pendente = {**ENTRADA, "no_ranking": False, "pendente": True, "foto_url": None}
    with patch("routers.upload.get_pool",                          AsyncMock(return_value=AsyncMock())), \
         patch("routers.upload.rl.checar_rate_limit",              AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score",           AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",                    AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir",              AsyncMock(return_value=entrada_pendente)), \
         patch("routers.upload._slug_from_id",                     AsyncMock(return_value="pac-man")):
        resp = await client.post(URL_API,
            data={"nick":"P1","pontuacao":"5000","jogo_id":JOGO_ID})
    assert resp.status_code == 201
    assert resp.json()["pendente"] is True
    assert "análise" in resp.json()["mensagem"]


@pytest.mark.asyncio
async def test_rate_limit_entra_como_pendente(client):
    with (p := _patches(pendente=True))[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8]:
        resp = await client.post(URL_API,
            data={"nick":"Spam","pontuacao":"1000","jogo_id":JOGO_ID},
            files=[("foto",("f.jpg",io.BytesIO(make_jpeg_bytes()),"image/jpeg"))])
    assert resp.status_code == 201
    assert resp.json()["pendente"] is True


@pytest.mark.asyncio
async def test_pendente_nao_publica_sse(client):
    broker_mock = AsyncMock()
    with patch("routers.upload.get_pool",                          AsyncMock(return_value=AsyncMock())), \
         patch("routers.upload.storage.upload_foto",               AsyncMock(return_value=FOTO_URL)), \
         patch("routers.upload.rl.checar_rate_limit",              AsyncMock(return_value=True)), \
         patch("routers.upload.score_svc.validar_score",           AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish",                    broker_mock), \
         patch("routers.upload.entrada_repo.inserir",              AsyncMock(return_value={**ENTRADA,"pendente":True,"no_ranking":False})), \
         patch("routers.upload._slug_from_id",                     AsyncMock(return_value="pac-man")):
        await client.post(URL_API,
            data={"nick":"P","pontuacao":"1","jogo_id":JOGO_ID},
            files=[("foto",("f.jpg",io.BytesIO(make_jpeg_bytes()),"image/jpeg"))])
    broker_mock.assert_not_called()


@pytest.mark.asyncio
async def test_upload_normal_publica_sse(client):
    broker_mock = AsyncMock()
    with (p := _patches())[0], p[1], p[2], p[3], p[4], \
         patch("routers.upload.broker.publish", broker_mock), \
         p[6], p[7], p[8]:
        await client.post(URL_API,
            data={"nick":"P","pontuacao":"5000","jogo_id":JOGO_ID},
            files=[("foto",("f.jpg",io.BytesIO(make_jpeg_bytes()),"image/jpeg"))])
    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "novo_registro"
