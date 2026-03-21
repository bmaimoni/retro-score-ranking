import pytest
import io
from unittest.mock import AsyncMock, patch, MagicMock
from conftest import make_jpeg_bytes, make_png_bytes


JOGO_ID = "550e8400-e29b-41d4-a716-446655440000"
UPLOAD_URL = "/api/upload"


def _form(nick="Jogador1", pontuacao=10000, jogo_id=JOGO_ID):
    return {"nick": nick, "pontuacao": str(pontuacao), "jogo_id": jogo_id}


def _foto(conteudo=None, content_type="image/jpeg", filename="score.jpg"):
    data = conteudo or make_jpeg_bytes()
    return ("foto", (filename, io.BytesIO(data), content_type))


# ── Helpers de patch ──────────────────────────────────────────────────────────

def _patches_ok(pool_mock):
    """Contexto com todos os serviços mockados para o caminho feliz."""
    return [
        patch("routers.upload.get_pool", return_value=pool_mock),
        patch("routers.upload.storage.upload_foto",
              new_callable=lambda: AsyncMock(return_value="https://cdn.example.com/foto.jpg")),
        patch("routers.upload.rl.checar_rate_limit",
              new_callable=lambda: AsyncMock(return_value=False)),
        patch("routers.upload.score_svc.validar_score",
              new_callable=lambda: AsyncMock(return_value=None)),
        patch("routers.upload.nick_svc.marcar_anterior_como_superado",
              new_callable=lambda: AsyncMock(return_value=None)),
        patch("routers.upload.broker.publish",
              new_callable=lambda: AsyncMock(return_value=None)),
    ]


# ── Testes de validação de arquivo ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejeita_arquivo_acima_de_5mb(client):
    grande = b"x" * (5 * 1024 * 1024 + 1)
    resp = await client.post(
        UPLOAD_URL,
        data=_form(),
        files=[("foto", ("big.jpg", io.BytesIO(grande), "image/jpeg"))],
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_rejeita_pdf_com_extensao_jpg(client):
    """Valida por magic bytes, não pela extensão declarada."""
    pdf_bytes = b"%PDF-1.4 fake content"
    resp = await client.post(
        UPLOAD_URL,
        data=_form(),
        files=[("foto", ("score.jpg", io.BytesIO(pdf_bytes), "image/jpeg"))],
    )
    assert resp.status_code == 422
    assert "Formato inválido" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_aceita_png_valido(client, fake_pool):
    import uuid
    fake_pool.fetchrow = AsyncMock(return_value={
        "id": str(uuid.uuid4()), "nick": "P1", "pontuacao": 5000,
        "foto_url": "https://cdn.example.com/f.png",
        "no_ranking": True, "pendente": False, "criado_em": "2024-01-01",
    })

    patches = _patches_ok(fake_pool)
    ctx = [p.__enter__() if hasattr(p, '__enter__') else p for p in patches]

    # Usa unittest.mock.patch como contexto manual
    with patch("routers.upload.get_pool", AsyncMock(return_value=fake_pool)), \
         patch("routers.upload.storage.upload_foto", AsyncMock(return_value="https://cdn.example.com/f.png")), \
         patch("routers.upload.rl.checar_rate_limit", AsyncMock(return_value=False)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish", AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir", AsyncMock(return_value={
             "id": str(uuid.uuid4()), "nick": "P1", "pontuacao": 5000,
             "foto_url": "https://cdn.example.com/f.png",
             "no_ranking": True, "pendente": False, "criado_em": "2024-01-01",
         })), \
         patch("routers.upload._slug_from_id", AsyncMock(return_value="pac-man")), \
         patch("routers.upload.jogo_repo.buscar_por_slug", AsyncMock(return_value={"slug": "pac-man"})):

        resp = await client.post(
            UPLOAD_URL,
            data=_form(),
            files=[_foto(make_png_bytes(), "image/png", "score.png")],
        )

    assert resp.status_code == 201


# ── Testes de lógica de negócio ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_pendente_quando_rate_limit_atingido(client, fake_pool):
    import uuid
    entrada_id = str(uuid.uuid4())

    with patch("routers.upload.get_pool", AsyncMock(return_value=fake_pool)), \
         patch("routers.upload.storage.upload_foto", AsyncMock(return_value="https://cdn.example.com/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit", AsyncMock(return_value=True)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish", AsyncMock(return_value=None)), \
         patch("routers.upload.entrada_repo.inserir", AsyncMock(return_value={
             "id": entrada_id, "nick": "Spam", "pontuacao": 1000,
             "foto_url": "https://cdn.example.com/f.jpg",
             "no_ranking": False, "pendente": True, "criado_em": "2024-01-01",
         })), \
         patch("routers.upload._slug_from_id", AsyncMock(return_value="pac-man")):

        resp = await client.post(
            UPLOAD_URL,
            data=_form(nick="Spam"),
            files=[_foto()],
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["pendente"] is True
    assert "análise" in data["mensagem"]


@pytest.mark.asyncio
async def test_upload_nao_publica_sse_quando_pendente(client, fake_pool):
    import uuid
    broker_mock = AsyncMock()

    with patch("routers.upload.get_pool", AsyncMock(return_value=fake_pool)), \
         patch("routers.upload.storage.upload_foto", AsyncMock(return_value="https://cdn.example.com/f.jpg")), \
         patch("routers.upload.rl.checar_rate_limit", AsyncMock(return_value=True)), \
         patch("routers.upload.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.upload.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.upload.broker.publish", broker_mock), \
         patch("routers.upload.entrada_repo.inserir", AsyncMock(return_value={
             "id": str(uuid.uuid4()), "nick": "P", "pontuacao": 1,
             "foto_url": "https://cdn.example.com/f.jpg",
             "no_ranking": False, "pendente": True, "criado_em": "2024-01-01",
         })), \
         patch("routers.upload._slug_from_id", AsyncMock(return_value="pac-man")):

        await client.post(
            UPLOAD_URL,
            data=_form(),
            files=[_foto()],
        )

    # SSE NÃO deve ser publicado para entradas pendentes
    broker_mock.assert_not_called()


# ── Testes de campos obrigatórios ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rejeita_sem_nick(client):
    resp = await client.post(
        UPLOAD_URL,
        data={"pontuacao": "1000", "jogo_id": JOGO_ID},
        files=[_foto()],
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejeita_score_zero(client):
    resp = await client.post(
        UPLOAD_URL,
        data={"nick": "X", "pontuacao": "0", "jogo_id": JOGO_ID},
        files=[_foto()],
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejeita_score_negativo(client):
    resp = await client.post(
        UPLOAD_URL,
        data={"nick": "X", "pontuacao": "-100", "jogo_id": JOGO_ID},
        files=[_foto()],
    )
    assert resp.status_code == 422
