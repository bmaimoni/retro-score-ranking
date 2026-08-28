"""
Router público de telões — acessível sem autenticação.
Prefixo: /api/teloes/{slug}

Endpoints:
  GET /api/teloes/{slug}/config → configuração de exibição do telão

Ver docs/EVENTOS_SPEC.md §3-5: um telão aponta pra exatamente um event OU
um placar, mostra top_n posições fixas (sem paginação — é uma tela grande,
não navegável), e escolhe seus próprios games/ordem via telao_jogos.
"""
from fastapi import APIRouter, Depends, HTTPException
from utils.db import get_pool
import repositories.telao as telao_repo

router = APIRouter(prefix="/api/teloes", tags=["telao-publico"])


@router.get("/{slug}/config")
async def get_config_telao(slug: str, pool=Depends(get_pool)):
    """
    Configuração de exibição de um telão: quantas posições mostrar
    (top_n), e por quais games girar o carrossel. O frontend usa
    event_slug ou placar_slug (exatamente um dos dois vem preenchido)
    para buscar o ranking de cada game em /api/e/{slug}/ranking/{game_slug}
    ou /api/p/{slug}/ranking/{game_slug}.
    """
    config = await telao_repo.buscar_config_por_slug(pool, slug)
    if not config:
        raise HTTPException(status_code=404, detail="Telão não encontrado")
    return config
