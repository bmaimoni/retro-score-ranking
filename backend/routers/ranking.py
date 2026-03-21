from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from utils.db import get_pool
from services.sse import broker
import repositories.jogo as jogo_repo
import repositories.entrada as entrada_repo

router = APIRouter(prefix="/api", tags=["ranking"])


@router.get("/ranking/{slug}")
async def get_ranking(slug: str, pool=Depends(get_pool)):
    """
    Snapshot atual do ranking de um jogo.
    Retorna entradas visíveis, não superadas, não pendentes, ordenadas por score.
    """
    jogo = await jogo_repo.buscar_por_slug(pool, slug)
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    entradas = await entrada_repo.listar_ranking(pool, str(jogo["id"]))
    return {"jogo": jogo, "entradas": entradas}


@router.get("/events/ranking/{slug}")
async def sse_ranking(slug: str, pool=Depends(get_pool)):
    """
    Stream SSE do ranking ao vivo.
    O cliente conecta uma vez e recebe eventos em tempo real:
      - novo_registro: uma nova entrada entrou no ranking
      - ocultar:       uma entrada foi ocultada pelo moderador
      - reativar:      uma entrada foi reativada pelo moderador
    """
    jogo = await jogo_repo.buscar_por_slug(pool, slug)
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    return StreamingResponse(
        broker.subscribe(slug),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # desabilita buffer do nginx
            "Connection": "keep-alive",
        },
    )
