"""
Router público de marcas — acessível sem autenticação.
Prefixo: /api/marcas

Ver docs/BACKLOG_2026.md §2 item 2.1 e ponto cego #2: quando
index.html não recebe ?evento= na URL (sem fallback hardcoded desde a
Fase 6), precisa de uma forma de descobrir pra qual marca/evento
mandar o visitante.
"""
from fastapi import APIRouter, Depends
from utils.db import get_pool
import repositories.marca  as marca_repo
import repositories.evento as evento_repo

router = APIRouter(prefix="/api/marcas", tags=["marcas-publico"])


@router.get("/com-evento-ativo")
async def listar_marcas_com_evento_ativo(pool=Depends(get_pool)):
    """
    Marcas com pelo menos um evento ativo+público, cada uma já com o
    slug do evento pra onde mandar o visitante — o mesmo "evento mais
    recente/ativo da marca" usado pelo QR em ranking agregado
    (evento_repo.buscar_evento_envio_atual_da_marca, Fase 4). Marca sem
    evento resolvível (não deveria acontecer, dado o filtro da query)
    fica de fora da lista em vez de quebrar a resposta.
    """
    marcas = await marca_repo.listar_com_evento_ativo(pool)
    resultado = []
    for m in marcas:
        evento = await evento_repo.buscar_evento_envio_atual_da_marca(pool, str(m["id"]))
        if evento:
            resultado.append({**m, "evento_slug": evento["slug"]})
    return resultado
