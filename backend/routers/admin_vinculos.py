"""
Router admin de admin_vinculos — hoje requer super-admin em toda rota.
Prefixo: /api/admin/vinculos

NOTA: docs/PERMISSOES_SPEC.md decisão #5 prevê admin conceder/revogar
vínculo dentro da própria marca (não só super) — ainda não implementado
aqui, é o próximo incremento sobre este router. Por ora o comportamento
é o herdado de MARCAS_SPEC.md §6 (só super), só com o schema atualizado
pra migration 019 (nivel no lugar de evento_id/escopo='evento').
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from middleware.auth import require_admin, AdminContext
from utils.db import get_pool
import repositories.admin_vinculo as admin_vinculo_repo
import auth.repository as auth_repo

router = APIRouter(prefix="/api/admin/vinculos", tags=["admin-vinculos"])

ESCOPOS_VALIDOS = {"super", "marca"}
NIVEIS_VALIDOS = {"admin", "moderador"}


class VinculoCreate(BaseModel):
    email:    EmailStr  # a pessoa precisa já ter logado alguma vez com este e-mail
    escopo:   str
    marca_id: str | None = None
    nivel:    str | None = None

    @field_validator("escopo")
    @classmethod
    def valida_escopo(cls, v):
        if v not in ESCOPOS_VALIDOS:
            raise ValueError(f"escopo deve ser um de {sorted(ESCOPOS_VALIDOS)}")
        return v

    @field_validator("nivel")
    @classmethod
    def valida_nivel(cls, v):
        if v is not None and v not in NIVEIS_VALIDOS:
            raise ValueError(f"nivel deve ser um de {sorted(NIVEIS_VALIDOS)}")
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
    if dados.escopo == "marca" and not dados.nivel:
        raise HTTPException(status_code=422, detail="escopo='marca' exige nivel")
    if dados.escopo == "super" and (dados.marca_id or dados.nivel):
        raise HTTPException(status_code=422, detail="escopo='super' não aceita marca_id nem nivel")

    usuario = await auth_repo.buscar_usuario_por_email(pool, dados.email.lower().strip())
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Essa pessoa ainda não tem conta — ela precisa logar pelo menos uma vez "
                   "(Google ou Magic Link) com esse e-mail antes de virar administradora.",
        )

    try:
        return await admin_vinculo_repo.criar(
            pool, usuario["id"], dados.escopo, dados.nivel, dados.marca_id,
        )
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Marca não encontrada")
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
