import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO


def _make_upload(content=b"img", content_type="image/jpeg"):
    """Cria um UploadFile sem tentar setar content_type via property."""
    from fastapi import UploadFile
    f = UploadFile(filename="test.jpg", file=BytesIO(content))
    # content_type é read-only em versões novas do FastAPI
    # passamos via headers em vez de setar diretamente
    object.__setattr__(f, '_content_type', content_type)
    # Monkey-patch a property para retornar nosso valor
    type(f).content_type = property(lambda self: getattr(self, '_content_type', 'image/jpeg'))
    return f


@pytest.mark.asyncio
async def test_upload_ok_retorna_url_publica():
    from services.storage import upload_foto
    foto = _make_upload()
    mock_resp = MagicMock(status_code=200, text="ok")

    with patch("services.storage.get_settings") as cfg, \
         patch("services.storage.httpx.AsyncClient") as mock_client:
        cfg.return_value.supabase_url = "https://proj.supabase.co"
        cfg.return_value.supabase_service_key = "key123"
        cfg.return_value.storage_bucket = "fotos-ranking"
        client_mock = MagicMock()
        client_mock.post = AsyncMock(return_value=mock_resp)
        mock_client.return_value.__aenter__ = AsyncMock(return_value=client_mock)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        url = await upload_foto(foto)

    assert url.startswith("https://proj.supabase.co/storage/v1/object/public/fotos-ranking/")
    assert url.endswith(".jpg")


@pytest.mark.asyncio
async def test_upload_falha_levanta_runtime_error():
    from services.storage import upload_foto
    foto = _make_upload()
    mock_resp = MagicMock(status_code=400, text='{"error":"bucket not found"}')

    with patch("services.storage.get_settings") as cfg, \
         patch("services.storage.httpx.AsyncClient") as mock_client:
        cfg.return_value.supabase_url = "https://proj.supabase.co"
        cfg.return_value.supabase_service_key = "key"
        cfg.return_value.storage_bucket = "fotos-ranking"
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=mock_resp))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        with pytest.raises(RuntimeError, match="Falha no upload: 400"):
            await upload_foto(foto)


@pytest.mark.asyncio
async def test_content_type_none_usa_jpeg_como_fallback():
    from services.storage import upload_foto
    foto = _make_upload(content_type=None)
    mock_resp = MagicMock(status_code=200, text="ok")

    with patch("services.storage.get_settings") as cfg, \
         patch("services.storage.httpx.AsyncClient") as mock_client:
        cfg.return_value.supabase_url = "https://proj.supabase.co"
        cfg.return_value.supabase_service_key = "key"
        cfg.return_value.storage_bucket = "fotos-ranking"
        client_mock = MagicMock()
        client_mock.post = AsyncMock(return_value=mock_resp)
        mock_client.return_value.__aenter__ = AsyncMock(return_value=client_mock)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        url = await upload_foto(foto)

    _, kwargs = client_mock.post.call_args
    assert kwargs.get("headers", {}).get("Content-Type") == "image/jpeg"
    assert url.endswith(".jpg")


@pytest.mark.asyncio
async def test_png_gera_extensao_png():
    from services.storage import upload_foto
    foto = _make_upload(content_type="image/png")
    mock_resp = MagicMock(status_code=200, text="ok")

    with patch("services.storage.get_settings") as cfg, \
         patch("services.storage.httpx.AsyncClient") as mock_client:
        cfg.return_value.supabase_url = "https://x.supabase.co"
        cfg.return_value.supabase_service_key = "key"
        cfg.return_value.storage_bucket = "fotos-ranking"
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=mock_resp))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        url = await upload_foto(foto)

    assert url.endswith(".png")