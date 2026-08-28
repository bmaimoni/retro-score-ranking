from fastapi import APIRouter, Depends
from utils.db import get_pool
import repositories.game as repo

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("")
async def listar_games(pool=Depends(get_pool)):
    """Lista todos os games ativos para preencher o seletor no frontend."""
    return await repo.listar_ativos(pool)

import repositories.event_config as config_repo

@router.get("/config")
async def get_config_publica(pool=Depends(get_pool)):
    """Retorna configurações públicas do event para o frontend de upload."""
    return await config_repo.get_publico(pool)