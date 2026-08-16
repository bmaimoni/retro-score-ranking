"""
Router admin de placares — requer autenticação.
Prefixo: /api/admin/placares

Ver docs/EVENTOS_SPEC.md §3: o placar global é único e seedado por
migração (não é criado aqui — o índice único parcial no banco impede
um segundo). Este router gerencia apenas placares customizados e a
membership de eventos neles.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import repositories.placar as placar_repo
from utils.db import get_pool
from middleware.auth import require_admin

router = APIRouter(prefix="/api/admin/placares", tags=["admin-placares"])


class PlacarCreate(BaseModel):
    nome: str
    slug: str


class PlacarEventoUpdate(BaseModel):
    ativo: bool | None = None


# ── CRUD de placares customizados ─────────────────────────────

@router.get("")
async def listar_placares(pool=Depends(get_pool), _=Depends(require_admin)):
    return await placar_repo.listar_todos(pool)


@router.post("", status_code=201)
async def criar_placar(
    dados: PlacarCreate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Cria um placar customizado (o placar global já existe, seedado por migração)."""
    try:
        return await placar_repo.criar(pool, dados.nome, dados.slug)
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Slug já existe")
        raise


# ── Membership de eventos no placar ───────────────────────────

@router.get("/{placar_id}/eventos")
async def listar_eventos_do_placar(
    placar_id: str,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Eventos vinculados ao placar (ativos e inativos)."""
    return await placar_repo.listar_eventos_do_placar(pool, placar_id)


@router.post("/{placar_id}/eventos/{evento_id}", status_code=201)
async def adicionar_evento_ao_placar(
    placar_id: str,
    evento_id: str,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Vincula um evento ao placar. Se já existir, reativa."""
    try:
        return await placar_repo.adicionar_evento(pool, placar_id, evento_id)
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Placar ou evento não encontrado")
        raise


@router.patch("/{placar_id}/eventos/{evento_id}")
async def atualizar_evento_do_placar(
    placar_id: str,
    evento_id: str,
    dados: PlacarEventoUpdate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """
    Atualiza ativo de um evento no placar — usado para "remover"
    (ativo=false) sem DELETE físico (app_user não tem essa permissão em
    placar_eventos, ver migration 012) e para reativar (ativo=true).
    """
    resultado = await placar_repo.remover_evento(pool, placar_id, evento_id) \
        if dados.ativo is False else \
        await placar_repo.adicionar_evento(pool, placar_id, evento_id)
    if not resultado:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    return resultado
