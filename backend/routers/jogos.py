from fastapi import APIRouter, Depends
from utils.db import get_pool
import repositories.jogo as repo

router = APIRouter(prefix="/api/jogos", tags=["jogos"])


@router.get("")
async def listar_jogos(pool=Depends(get_pool)):
    """Lista todos os jogos ativos para preencher o seletor no frontend."""
    return await repo.listar_ativos(pool)
