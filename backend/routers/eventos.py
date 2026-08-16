"""
Router admin de eventos — requer autenticação.
Prefixo: /api/admin/eventos
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from datetime import datetime
from utils.db import get_pool
from middleware.auth import require_admin
import repositories.evento      as evento_repo
import repositories.evento_jogo as evento_jogo_repo

router = APIRouter(prefix="/api/admin/eventos", tags=["admin-eventos"])


class EventoCreate(BaseModel):
    nome:         str
    slug:         str
    ativo:        bool = True
    publico:      bool = True
    logo_url:     str | None = None
    cor_primaria: str | None = None
    data_inicio:  datetime
    data_fim:     datetime

    @field_validator("data_fim")
    @classmethod
    def data_fim_apos_inicio(cls, v, info):
        inicio = info.data.get("data_inicio")
        if inicio and v <= inicio:
            raise ValueError("data_fim deve ser posterior a data_inicio")
        return v


class EventoUpdate(BaseModel):
    nome:         str | None = None
    ativo:        bool | None = None
    publico:      bool | None = None
    logo_url:     str | None = None
    cor_primaria: str | None = None
    data_inicio:  datetime | None = None
    data_fim:     datetime | None = None


class EventoJogoUpdate(BaseModel):
    ativo: bool | None = None
    ordem: int | None = None


# ── CRUD de eventos ───────────────────────────────────────────

@router.get("")
async def listar_eventos(pool=Depends(get_pool), _=Depends(require_admin)):
    return await evento_repo.listar(pool)


@router.get("/ativos")
async def listar_ativos(pool=Depends(get_pool)):
    """Público — usado pelo frontend para listar eventos ativos."""
    return await evento_repo.listar_ativos(pool)


@router.post("", status_code=201)
async def criar_evento(
    dados: EventoCreate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    try:
        return await evento_repo.criar(pool, dados.model_dump())
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Slug já existe")
        raise


@router.patch("/{evento_id}")
async def atualizar_evento(
    evento_id: str,
    dados: EventoUpdate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    evento = await evento_repo.atualizar(
        pool, evento_id, dados.model_dump(exclude_none=True)
    )
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return evento


# ── Gestão de jogos por evento ────────────────────────────────

@router.get("/{evento_id}/jogos")
async def listar_jogos_do_evento(
    evento_id: str,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Lista jogos vinculados ao evento (ativos e inativos)."""
    return await evento_jogo_repo.listar_por_evento(pool, evento_id)


@router.post("/{evento_id}/jogos/{jogo_id}", status_code=201)
async def adicionar_jogo_ao_evento(
    evento_id: str,
    jogo_id: str,
    ordem: int = 0,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Adiciona jogo ao evento. Se já existir, reativa."""
    try:
        return await evento_jogo_repo.adicionar(pool, evento_id, jogo_id, ordem)
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Evento ou jogo não encontrado")
        raise


@router.patch("/{evento_id}/jogos/{jogo_id}")
async def atualizar_jogo_do_evento(
    evento_id: str,
    jogo_id: str,
    dados: EventoJogoUpdate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Atualiza ativo e/ou ordem de um jogo num evento."""
    resultado = await evento_jogo_repo.atualizar(
        pool, evento_id, jogo_id, dados.model_dump(exclude_none=True)
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    return resultado