from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
from utils.db import get_pool
from middleware.auth import require_admin as verificar_admin
import repositories.evento as evento_repo

router = APIRouter(prefix="/api/admin/eventos", tags=["eventos"])


class EventoCreate(BaseModel):
    nome: str
    slug: str
    ativo: bool = True
    data_inicio: datetime | None = None
    data_fim: datetime | None = None


class EventoUpdate(BaseModel):
    nome: str | None = None
    ativo: bool | None = None
    data_inicio: datetime | None = None
    data_fim: datetime | None = None


@router.get("")
async def listar_eventos(pool=Depends(get_pool), _=Depends(verificar_admin)):
    return await evento_repo.listar(pool)


@router.get("/ativos")
async def listar_ativos(pool=Depends(get_pool)):
    """Público — usado pelo frontend para mostrar evento atual."""
    return await evento_repo.listar_ativos(pool)


@router.post("", status_code=201)
async def criar_evento(
    dados: EventoCreate,
    pool=Depends(get_pool),
    _=Depends(verificar_admin),
):
    try:
        evento = await evento_repo.criar(pool, dados.model_dump())
        return evento
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Slug já existe")
        raise


@router.patch("/{evento_id}")
async def atualizar_evento(
    evento_id: str,
    dados: EventoUpdate,
    pool=Depends(get_pool),
    _=Depends(verificar_admin),
):
    evento = await evento_repo.atualizar(pool, evento_id, dados.model_dump(exclude_none=True))
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return evento