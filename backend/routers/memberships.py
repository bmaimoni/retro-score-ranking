"""
Router admin de memberships — concessão/revogação de acesso
administrativo. Prefixo: /api/admin/vinculos

Ver docs/PERMISSOES_SPEC.md §2 (decisões #5, #9, #10, #12) e §5 (riscos
identificados — em especial risco #1, escalonamento cross-arena):

- Conceder (POST) ou reativar (PATCH ativo=true) vínculo scope='marca':
  super sempre pode; admin só na PRÓPRIA arena, pra role admin ou
  moderador. Só super concede scope='super' ou mexe fora da própria
  arena.
- Revogar (PATCH ativo=false): moderador de qualquer nível só é
  revogado por admin (ou super) da mesma arena. Um vínculo role='admin'
  só é revogado pelo titular (owner_user_id) da arena ou por super —
  admin comum NUNCA revoga outro admin (decisão #9). Revogar o vínculo
  do titular atual é bloqueado (decisão #10) — precisa transferir
  titularidade primeiro (endpoint ainda não implementado).
- GET: super lista tudo; admin não-super lista só os vínculos
  (admin E moderador) das arenas onde ele mesmo tem role='admin' —
  nunca vínculos scope='super', nunca de arena onde só é moderador ou
  não tem vínculo (docs/PERMISSOES_SPEC.md §8.2 — corrige o bloqueio
  total que existia antes e impedia até o dono da própria arena ver
  quem ele mesmo administra).
- Toda concessão/revogação grava em membership_audit_log (decisão #12).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from middleware.auth import require_admin, AdminContext
from utils.db import get_pool
import repositories.membership as membership_repo
import repositories.arena as arena_repo
import auth.repository as auth_repo

router = APIRouter(prefix="/api/admin/vinculos", tags=["admin-vinculos"])

SCOPES_VALIDOS = {"super", "marca"}
ROLES_VALIDOS = {"admin", "moderador"}


class VinculoCreate(BaseModel):
    email:    EmailStr  # a pessoa precisa já ter logado alguma vez com este e-mail
    scope:   str
    arena_id: str | None = None
    role:    str | None = None

    @field_validator("scope")
    @classmethod
    def valida_scope(cls, v):
        if v not in SCOPES_VALIDOS:
            raise ValueError(f"scope deve ser um de {sorted(SCOPES_VALIDOS)}")
        return v

    @field_validator("role")
    @classmethod
    def valida_role(cls, v):
        if v is not None and v not in ROLES_VALIDOS:
            raise ValueError(f"role deve ser um de {sorted(ROLES_VALIDOS)}")
        return v


class VinculoUpdate(BaseModel):
    ativo: bool


def _pode_conceder(admin: AdminContext, scope: str, arena_id: str | None) -> bool:
    """
    Quem pode CONCEDER (criar ou reativar) um vínculo com este
    scope/arena. super sempre pode; admin só concede scope='marca' e
    só na própria arena (decisão #5) — nunca scope='super', nunca fora
    do que ele mesmo administra. Cobre tanto 'admin concede admin'
    quanto 'admin concede moderador': a spec não distingue os dois pra
    concessão, só pra revogação (ver _pode_revogar).
    """
    if admin.super:
        return True
    if scope == "super":
        return False
    return admin.eh_admin_na_arena(arena_id)


def _pode_revogar(admin: AdminContext, vinculo: dict, owner_user_id: str | None) -> bool:
    """
    Quem pode REVOGAR um vínculo existente. Mais restritivo que
    _pode_conceder pro caso role='admin': só o titular da arena (ou
    super) revoga outro admin — admin comum revoga só moderador
    (decisão #9). A trava de "não revogar o titular atual" é checada
    à parte, antes desta função (é bloqueio de integridade, não de
    permissão — vale até pra super).
    """
    if admin.super:
        return True
    if vinculo["scope"] == "super":
        return False
    if not admin.eh_admin_na_arena(vinculo["arena_id"]):
        return False
    if vinculo["role"] == "moderador":
        return True
    return admin.user_id is not None and owner_user_id is not None and str(admin.user_id) == str(owner_user_id)


@router.get("")
async def listar_vinculos(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """super vê todos; admin não-super só os vínculos das arenas onde
    ele mesmo tem role='admin' — é a única situação em que ele tem
    qualquer ação de gestão disponível nesta lista (conceder/revogar
    moderador sempre; conceder/revogar outro admin só se também for o
    titular). Arena onde só é moderador não aparece: não há nada que
    ele possa fazer ali."""
    if admin.super:
        return await membership_repo.listar_todos(pool)
    arena_ids = [v["arena_id"] for v in admin.vinculos if v["role"] == "admin"]
    return await membership_repo.listar_por_arenas(pool, arena_ids)


@router.post("", status_code=201)
async def criar_vinculo(
    dados: VinculoCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    if dados.scope == "marca" and not dados.arena_id:
        raise HTTPException(status_code=422, detail="scope='marca' exige arena_id")
    if dados.scope == "marca" and not dados.role:
        raise HTTPException(status_code=422, detail="scope='marca' exige role")
    if dados.scope == "super" and (dados.arena_id or dados.role):
        raise HTTPException(status_code=422, detail="scope='super' não aceita arena_id nem role")

    if not _pode_conceder(admin, dados.scope, dados.arena_id):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para conceder vínculo com este scope/arena",
        )

    usuario = await auth_repo.buscar_usuario_por_email(pool, dados.email.lower().strip())
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Essa pessoa ainda não tem conta — ela precisa logar pelo menos uma vez "
                   "(Google ou Magic Link) com esse e-mail antes de virar administradora.",
        )

    try:
        vinculo = await membership_repo.criar(
            pool, usuario["id"], dados.scope, dados.role, dados.arena_id,
        )
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Marca não encontrada")
        raise

    await membership_repo.registrar_auditoria(
        pool, acao="concedido", user_alvo_id=usuario["id"], realizado_por=admin.identificador,
        arena_id=dados.arena_id, role=dados.role,
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
    vinculo = await membership_repo.buscar_por_id(pool, vinculo_id)
    if not vinculo:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")

    owner_user_id = None
    if vinculo["scope"] == "marca":
        owner_user_id = await arena_repo.buscar_owner_user_id(pool, vinculo["arena_id"])

    if dados.ativo:
        if not _pode_conceder(admin, vinculo["scope"], vinculo["arena_id"]):
            raise HTTPException(status_code=403, detail="Sem permissão para reativar este vínculo")
    else:
        if owner_user_id and str(vinculo["user_id"]) == str(owner_user_id):
            raise HTTPException(
                status_code=409,
                detail="Não é possível revogar o vínculo do titular da arena — "
                       "transfira a titularidade primeiro",
            )
        if not _pode_revogar(admin, vinculo, owner_user_id):
            raise HTTPException(status_code=403, detail="Sem permissão para revogar este vínculo")

    atualizado = await membership_repo.atualizar_ativo(pool, vinculo_id, dados.ativo)

    await membership_repo.registrar_auditoria(
        pool, acao="concedido" if dados.ativo else "revogado",
        user_alvo_id=vinculo["user_id"], realizado_por=admin.identificador,
        arena_id=vinculo["arena_id"], role=vinculo["role"],
    )
    return atualizado
