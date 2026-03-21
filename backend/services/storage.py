import uuid
import httpx
from fastapi import UploadFile
from config import get_settings
import structlog

log = structlog.get_logger()


async def upload_foto(foto: UploadFile) -> str:
    """
    Faz upload da foto para o bucket do Supabase Storage.

    Retorna a URL pública permanente.
    Arquivos NUNCA são deletados — evidência de moderação preservada.
    """
    settings = get_settings()

    ext = "jpg" if foto.content_type == "image/jpeg" else "png"
    filename = f"{uuid.uuid4()}.{ext}"
    conteudo = await foto.read()

    url = f"{settings.supabase_url}/storage/v1/object/{settings.storage_bucket}/{filename}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": foto.content_type,
        "x-upsert": "false",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, content=conteudo, headers=headers)

    if resp.status_code not in (200, 201):
        log.error("storage_upload_failed", status=resp.status_code, body=resp.text)
        raise RuntimeError(f"Falha no upload: {resp.status_code}")

    public_url = (
        f"{settings.supabase_url}/storage/v1/object/public/"
        f"{settings.storage_bucket}/{filename}"
    )
    log.info("storage_upload_ok", filename=filename)
    return public_url
