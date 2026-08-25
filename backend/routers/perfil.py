"""
Router de perfil de usuário — requer login (sessão de visitante comum,
não admin). Prefixo: /api/perfil

Ver docs/BACKLOG_2026.md §1 (itens 1.3/1.8).
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from utils.db import get_pool
import auth.service as auth_svc
import auth.repository as auth_repo
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


class NickTroca(BaseModel):
    nick: str

    @field_validator("nick")
    @classmethod
    def nick_nao_vazio(cls, v):
        if not v.strip():
            raise ValueError("nick não pode ser vazio")
        return v


@router.get("")
async def ver_perfil(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    perfil = await usuario_repo.buscar_perfil(pool, usuario["id"])
    claim_atual = await auth_repo.buscar_claim_ativo_do_usuario(pool, usuario["id"])
    perfil["nick_atual"] = claim_atual["nick"] if claim_atual else None
    return perfil


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


@router.post("/nick", status_code=201)
async def trocar_nick(
    dados: NickTroca,
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    """
    Troca deliberada de nick (docs/NICKNAME_SPEC.md) — distinta do
    claim implícito que acontece no upload de score. Cooldown de 30
    dias entre trocas; primeira reivindicação nunca conta como troca.
    """
    try:
        return await auth_svc.trocar_nick(pool, usuario["id"], dados.nick)
    except auth_svc.NickTrocaEmCooldownError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except auth_svc.NickJaReivindicadoError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
