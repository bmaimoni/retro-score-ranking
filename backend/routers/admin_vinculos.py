"""
Router admin de admin_vinculos — concessão/revogação de acesso
administrativo. Prefixo: /api/admin/vinculos

Ver docs/PERMISSOES_SPEC.md §2 (decisões #5, #9, #10, #12) e §5 (riscos
identificados — em especial risco #1, escalonamento cross-marca):

- Conceder (POST) ou reativar (PATCH ativo=true) vínculo escopo='marca':
  super sempre pode; admin só na PRÓPRIA marca, pra nivel admin ou
  moderador. Só super concede escopo='super' ou mexe fora da própria
  marca.
- Revogar (PATCH ativo=false): moderador de qualquer nível só é
  revogado por admin (ou super) da mesma marca. Um vínculo nivel='admin'
  só é revogado pelo titular (dono_user_id) da marca ou por super —
  admin comum NUNCA revoga outro admin (decisão #9). Revogar o vínculo
  do titular atual é bloqueado (decisão #10) — precisa transferir
  titularidade primeiro (endpoint ainda não implementado).
- GET: super lista tudo; admin não-super lista só os vínculos
  (admin E moderador) das marcas onde ele mesmo tem nivel='admin' —
  nunca vínculos escopo='super', nunca de marca onde só é moderador ou
  não tem vínculo (docs/PERMISSOES_SPEC.md §8.2 — corrige o bloqueio
  total que existia antes e impedia até o dono da própria marca ver
  quem ele mesmo administra).
- Toda concessão/revogação grava em admin_vinculos_auditoria (decisão #12).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from middleware.auth import require_admin, AdminContext
from utils.db import get_pool
import repositories.admin_vinculo as admin_vinculo_repo
import repositories.marca as marca_repo
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


def _pode_conceder(admin: AdminContext, escopo: str, marca_id: str | None) -> bool:
    """
    Quem pode CONCEDER (criar ou reativar) um vínculo com este
    escopo/marca. super sempre pode; admin só concede escopo='marca' e
    só na própria marca (decisão #5) — nunca escopo='super', nunca fora
    do que ele mesmo administra. Cobre tanto 'admin concede admin'
    quanto 'admin concede moderador': a spec não distingue os dois pra
    concessão, só pra revogação (ver _pode_revogar).
    """
    if admin.super:
        return True
    if escopo == "super":
        return False
    return admin.eh_admin_na_marca(marca_id)


def _pode_revogar(admin: AdminContext, vinculo: dict, dono_user_id: str | None) -> bool:
    """
    Quem pode REVOGAR um vínculo existente. Mais restritivo que
    _pode_conceder pro caso nivel='admin': só o titular da marca (ou
    super) revoga outro admin — admin comum revoga só moderador
    (decisão #9). A trava de "não revogar o titular atual" é checada
    à parte, antes desta função (é bloqueio de integridade, não de
    permissão — vale até pra super).
    """
    if admin.super:
        return True
    if vinculo["escopo"] == "super":
        return False
    if not admin.eh_admin_na_marca(vinculo["marca_id"]):
        return False
    if vinculo["nivel"] == "moderador":
        return True
    return admin.user_id is not None and dono_user_id is not None and str(admin.user_id) == str(dono_user_id)


@router.get("")
async def listar_vinculos(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """super vê todos; admin não-super só os vínculos das marcas onde
    ele mesmo tem nivel='admin' — é a única situação em que ele tem
    qualquer ação de gestão disponível nesta lista (conceder/revogar
    moderador sempre; conceder/revogar outro admin só se também for o
    titular). Marca onde só é moderador não aparece: não há nada que
    ele possa fazer ali."""
    if admin.super:
        return await admin_vinculo_repo.listar_todos(pool)
    marca_ids = [v["marca_id"] for v in admin.vinculos if v["nivel"] == "admin"]
    return await admin_vinculo_repo.listar_por_marcas(pool, marca_ids)


@router.post("", status_code=201)
async def criar_vinculo(
    dados: VinculoCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    if dados.escopo == "marca" and not dados.marca_id:
        raise HTTPException(status_code=422, detail="escopo='marca' exige marca_id")
    if dados.escopo == "marca" and not dados.nivel:
        raise HTTPException(status_code=422, detail="escopo='marca' exige nivel")
    if dados.escopo == "super" and (dados.marca_id or dados.nivel):
        raise HTTPException(status_code=422, detail="escopo='super' não aceita marca_id nem nivel")

    if not _pode_conceder(admin, dados.escopo, dados.marca_id):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para conceder vínculo com este escopo/marca",
        )

    usuario = await auth_repo.buscar_usuario_por_email(pool, dados.email.lower().strip())
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Essa pessoa ainda não tem conta — ela precisa logar pelo menos uma vez "
                   "(Google ou Magic Link) com esse e-mail antes de virar administradora.",
        )

    try:
        vinculo = await admin_vinculo_repo.criar(
            pool, usuario["id"], dados.escopo, dados.nivel, dados.marca_id,
        )
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Marca não encontrada")
        raise

    await admin_vinculo_repo.registrar_auditoria(
        pool, acao="concedido", user_alvo_id=usuario["id"], realizado_por=admin.identificador,
        marca_id=dados.marca_id, nivel=dados.nivel,
    )
    return vinculo


@router.patch("/{vinculo_id}")
async def atualizar_vinculo(
    vinculo_id: str,
    dados: VinculoUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Ativa/desativa um vínculo — 'remover' é ativo=false (sem DELETE físico)."""
    vinculo = await admin_vinculo_repo.buscar_por_id(pool, vinculo_id)
    if not vinculo:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")

    dono_user_id = None
    if vinculo["escopo"] == "marca":
        dono_user_id = await marca_repo.buscar_dono_user_id(pool, vinculo["marca_id"])

    if dados.ativo:
        if not _pode_conceder(admin, vinculo["escopo"], vinculo["marca_id"]):
            raise HTTPException(status_code=403, detail="Sem permissão para reativar este vínculo")
    else:
        if dono_user_id and str(vinculo["user_id"]) == str(dono_user_id):
            raise HTTPException(
                status_code=409,
                detail="Não é possível revogar o vínculo do titular da marca — "
                       "transfira a titularidade primeiro",
            )
        if not _pode_revogar(admin, vinculo, dono_user_id):
            raise HTTPException(status_code=403, detail="Sem permissão para revogar este vínculo")

    atualizado = await admin_vinculo_repo.atualizar_ativo(pool, vinculo_id, dados.ativo)

    await admin_vinculo_repo.registrar_auditoria(
        pool, acao="concedido" if dados.ativo else "revogado",
        user_alvo_id=vinculo["user_id"], realizado_por=admin.identificador,
        marca_id=vinculo["marca_id"], nivel=vinculo["nivel"],
    )
    return atualizado
