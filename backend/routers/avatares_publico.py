from fastapi import APIRouter, Depends
from utils.db import get_pool
import repositories.avatar as avatar_repo

router = APIRouter(prefix="/api/avatares", tags=["avatares"])


@router.get("")
async def listar_avatares_ativos(pool=Depends(get_pool)):
    """Galeria de avatares disponíveis pro perfil escolher — só ativos."""
    return await avatar_repo.listar_ativos(pool)
