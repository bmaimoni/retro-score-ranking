"""
Router admin de avatares — CRUD exclusivo de super-admin.
Prefixo: /api/admin/avatares

Ver docs/BACKLOG_2026.md §1, ponto cego #3: galeria curada, upload
livre pelo usuário fica fora de escopo (precisaria de moderação de
imagem que não existe).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext
import repositories.avatar as avatar_repo

router = APIRouter(prefix="/api/admin/avatares", tags=["admin-avatares"])


class AvatarCreate(BaseModel):
    nome: str
    url:  str


class AvatarUpdate(BaseModel):
    ativo: bool


def _exigir_super(admin: AdminContext):
    if not admin.super:
        raise HTTPException(status_code=403, detail="Só super-admin pode gerenciar avatares")


@router.get("")
async def listar_avatares(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    _exigir_super(admin)
    return await avatar_repo.listar_todos(pool)


@router.post("", status_code=201)
async def criar_avatar(
    dados: AvatarCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    _exigir_super(admin)
    return await avatar_repo.criar(pool, dados.nome, dados.url)


@router.patch("/{avatar_id}")
async def atualizar_avatar(
    avatar_id: str,
    dados: AvatarUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Ativa/desativa — 'remover' é ativo=false (sem DELETE físico)."""
    _exigir_super(admin)
    avatar = await avatar_repo.atualizar_ativo(pool, avatar_id, dados.ativo)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar não encontrado")
    return avatar
