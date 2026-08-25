"""
Router de perfil de usuário — requer login (sessão de visitante comum,
não admin). Prefixo: /api/perfil

Ver docs/BACKLOG_2026.md §1 (itens 1.3/1.8).
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from utils.db import get_pool
import auth.service as auth_svc
import repositories.usuario as usuario_repo
import repositories.avatar as avatar_repo

router = APIRouter(prefix="/api/perfil", tags=["perfil"])


class PerfilUpdate(BaseModel):
    nome_completo:   str | None = None
    data_nascimento: date | None = None
    cidade:          str | None = None
    estado:          str | None = None
    telefone:        str | None = None
    avatar_id:       str | None = None


@router.get("")
async def ver_perfil(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    return await usuario_repo.buscar_perfil(pool, usuario["id"])


@router.patch("")
async def atualizar_perfil(
    dados: PerfilUpdate,
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    if dados.avatar_id:
        avatar = await avatar_repo.buscar_por_id(pool, dados.avatar_id)
        if not avatar or not avatar["ativo"]:
            raise HTTPException(status_code=422, detail="Avatar inválido ou desativado")

    perfil = await usuario_repo.atualizar_perfil(pool, usuario["id"], dados.model_dump(exclude_none=True))
    if not perfil:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return perfil
