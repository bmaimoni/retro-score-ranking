from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from utils.db import get_pool
from services.sse import broker
import repositories.game as game_repo
import repositories.entry as entry_repo

router = APIRouter(prefix="/api", tags=["ranking"])


@router.get("/ranking/lideres")
async def get_lideres(pool=Depends(get_pool)):
    """
    Retorna o top 1 de cada game ativo em uma única query.
    Deve vir ANTES de /ranking/{slug} para não ser capturado como slug.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (e.game_id)
            e.game_id,
            j.slug,
            e.nick,
            e.pontuacao
        FROM entries e
        JOIN games j ON j.id = e.game_id
        WHERE e.no_ranking = true
          AND e.superado   = false
          AND e.pendente   = false
          AND j.ativo      = true
        ORDER BY e.game_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC
        """
    )
    return {str(r["game_id"]): {"slug": r["slug"], "nick": r["nick"], "pontuacao": r["pontuacao"]} for r in rows}


@router.get("/ranking/{slug}")
async def get_ranking(slug: str, pool=Depends(get_pool)):
    """
    Snapshot atual do ranking de um game.
    Retorna entries visíveis, não superadas, não pendentes, ordenadas por score.
    """
    game = await game_repo.buscar_por_slug(pool, slug)
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    entries = await entry_repo.listar_ranking(pool, str(game["id"]))
    return {"game": game, "entries": entries}



@router.get("/ranking/{slug}/historico/{nick}")
async def get_historico_nick(slug: str, nick: str, pool=Depends(get_pool)):
    """
    Histórico completo de um nick em um game.
    Retorna todas as tentativas (ativas, superadas, arquivadas),
    ordenadas da mais recente para a mais antiga.
    """
    from services.nick import normalizar_nick
    game = await game_repo.buscar_por_slug(pool, slug)
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    nick_norm = normalizar_nick(nick)
    entries  = await entry_repo.historico_nick(pool, str(game["id"]), nick_norm)
    return {"game_slug": slug, "nick": nick, "historico": entries}

@router.get("/events/ranking/{slug}")
async def sse_ranking(slug: str, pool=Depends(get_pool)):
    """
    Stream SSE do ranking ao vivo.
    O cliente conecta uma vez e recebe events em tempo real:
      - novo_registro: uma nova entry entrou no ranking
      - ocultar:       uma entry foi ocultada pelo moderador
      - reativar:      uma entry foi reativada pelo moderador
    """
    game = await game_repo.buscar_por_slug(pool, slug)
    if not game:
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