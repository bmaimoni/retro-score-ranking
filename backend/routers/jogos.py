from fastapi import APIRouter, Depends
from utils.db import get_pool
import repositories.jogo as repo

router = APIRouter(prefix="/api/jogos", tags=["jogos"])


@router.get("")
async def listar_jogos(pool=Depends(get_pool)):
    """Lista todos os jogos ativos para preencher o seletor no frontend."""
    return await repo.listar_ativos(pool)

import repositories.evento_config as config_repo

@router.get("/config")
async def get_config_publica(pool=Depends(get_pool)):
    """Retorna configurações públicas do evento para o frontend de upload."""
    return await config_repo.get_publico(pool)