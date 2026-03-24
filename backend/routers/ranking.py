from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from utils.db import get_pool
from services.sse import broker
import repositories.jogo as jogo_repo
import repositories.entrada as entrada_repo

router = APIRouter(prefix="/api", tags=["ranking"])


@router.get("/ranking/lideres")
async def get_lideres(pool=Depends(get_pool)):
    """
    Retorna o top 1 de cada jogo ativo em uma única query.
    Deve vir ANTES de /ranking/{slug} para não ser capturado como slug.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (e.jogo_id)
            e.jogo_id,
            j.slug,
            e.nick,
            e.pontuacao
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        WHERE e.no_ranking = true
          AND e.superado   = false
          AND e.pendente   = false
          AND j.ativo      = true
        ORDER BY e.jogo_id, e.pontuacao DESC
        """
    )
    return {str(r["jogo_id"]): {"slug": r["slug"], "nick": r["nick"], "pontuacao": r["pontuacao"]} for r in rows}


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



@router.get("/ranking/{slug}/historico/{nick}")
async def get_historico_nick(slug: str, nick: str, pool=Depends(get_pool)):
    """
    Histórico completo de um nick em um jogo.
    Retorna todas as tentativas (ativas, superadas, arquivadas),
    ordenadas da mais recente para a mais antiga.
    """
    from services.nick import normalizar_nick
    jogo = await jogo_repo.buscar_por_slug(pool, slug)
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    nick_norm = normalizar_nick(nick)
    entradas  = await entrada_repo.historico_nick(pool, str(jogo["id"]), nick_norm)
    return {"jogo_slug": slug, "nick": nick, "historico": entradas}

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