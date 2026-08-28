"""
Router público de arenas — acessível sem autenticação.
Prefixo: /api/arenas

Ver docs/BACKLOG_2026.md §2 item 2.1 e ponto cego #2: quando
index.html não recebe ?event= na URL (sem fallback hardcoded desde a
Fase 6), precisa de uma forma de descobrir pra qual arena/event
mandar o visitante.
"""
from fastapi import APIRouter, Depends
from utils.db import get_pool
import repositories.arena  as arena_repo
import repositories.event as event_repo

router = APIRouter(prefix="/api/arenas", tags=["arenas-publico"])


@router.get("/eventos-abertos")
async def listar_eventos_abertos(pool=Depends(get_pool)):
    """
    Diretório de events com visibility='open' — alimenta a seção de
    descoberta da home institucional (Fase 8, ARENA_SPEC.md D.1/D.7).
    Cada item já linka direto pra play.html?evento={slug}.
    """
    return await event_repo.listar_abertos(pool)


@router.get("/com-event-ativo")
async def listar_arenas_com_event_ativo(pool=Depends(get_pool)):
    """
    Arenas com pelo menos um event ativo+público, cada uma já com o
    slug do event pra onde mandar o visitante — o mesmo "event mais
    recente/ativo da arena" usado pelo QR em ranking agregado
    (event_repo.buscar_event_envio_atual_da_arena, Fase 4). Arena sem
    event resolvível (não deveria acontecer, dado o filtro da query)
    fica de fora da lista em vez de quebrar a resposta.
    """
    arenas = await arena_repo.listar_com_event_ativo(pool)
    resultado = []
    for m in arenas:
        event = await event_repo.buscar_event_envio_atual_da_arena(pool, str(m["id"]))
        if event:
            resultado.append({**m, "event_slug": event["slug"]})
    return resultado
