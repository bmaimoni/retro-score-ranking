"""
Router admin de admin_vinculos — requer super-admin.
Prefixo: /api/admin/vinculos

Ver docs/MARCAS_SPEC.md §6: só super-admin cria/remove vínculo de
administração de outra pessoa. Um admin escopado (marca/evento) não
pode conceder acesso a mais ninguém.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from middleware.auth import require_admin, AdminContext
from utils.db import get_pool
import repositories.admin_vinculo as admin_vinculo_repo

router = APIRouter(prefix="/api/admin/vinculos", tags=["admin-vinculos"])

ESCOPOS_VALIDOS = {"super", "marca", "evento"}


class VinculoCreate(BaseModel):
    user_id:   str
    escopo:    str
    marca_id:  str | None = None
    evento_id: str | None = None

    @field_validator("escopo")
    @classmethod
    def valida_escopo(cls, v):
        if v not in ESCOPOS_VALIDOS:
            raise ValueError(f"escopo deve ser um de {sorted(ESCOPOS_VALIDOS)}")
        return v


class VinculoUpdate(BaseModel):
    ativo: bool


def _exigir_super(admin: AdminContext):
    if not admin.super:
        raise HTTPException(
            status_code=403,
            detail="Só super-admin pode gerenciar vínculos de outros administradores",
        )


@router.get("")
async def listar_vinculos(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    _exigir_super(admin)
    return await admin_vinculo_repo.listar_todos(pool)


@router.post("", status_code=201)
async def criar_vinculo(
    dados: VinculoCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    _exigir_super(admin)

    if dados.escopo == "marca" and not dados.marca_id:
        raise HTTPException(status_code=422, detail="escopo='marca' exige marca_id")
    if dados.escopo == "evento" and not dados.evento_id:
        raise HTTPException(status_code=422, detail="escopo='evento' exige evento_id")
    if dados.escopo == "super" and (dados.marca_id or dados.evento_id):
        raise HTTPException(status_code=422, detail="escopo='super' não aceita marca_id nem evento_id")

    try:
        return await admin_vinculo_repo.criar(
            pool, dados.user_id, dados.escopo, dados.marca_id, dados.evento_id,
        )
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Usuário, marca ou evento não encontrado")
        raise


@router.patch("/{vinculo_id}")
async def atualizar_vinculo(
    vinculo_id: str,
    dados: VinculoUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Ativa/desativa um vínculo — 'remover' é ativo=false (sem DELETE físico)."""
    _exigir_super(admin)

    vinculo = await admin_vinculo_repo.atualizar_ativo(pool, vinculo_id, dados.ativo)
    if not vinculo:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    return vinculo
