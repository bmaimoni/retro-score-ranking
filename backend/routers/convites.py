"""
Router público de aceite de convite de coadministração (Fase 10,
ARENA_SPEC.md Fase F). Prefixo: /api/convites

Distinto de /api/admin/arenas/{id}/convites (gestão da fila, exige já
ser admin da Arena) — aqui quem chega é o CONVIDADO, que pode nunca
ter tido acesso nenhum antes. Por isso fica fora de /api/admin e usa
require_authenticated_user (mesma dependency fraca criada na Fase 8
pro ovo-e-galinha de criar Arena, até agora sem outro uso).
"""
import hashlib
from fastapi import APIRouter, Depends, HTTPException
import auth.repository as auth_repo
import auth.service as auth_svc
import repositories.arena as arena_repo
import repositories.membership as membership_repo
from utils.db import get_pool
from middleware.auth import require_authenticated_user, AuthenticatedUser

router = APIRouter(prefix="/api/convites", tags=["convites"])


async def _resolver_convite_valido_ou_404(pool, token: str) -> dict:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    convite = await membership_repo.buscar_convite_valido_por_token_hash(pool, token_hash)
    if not convite:
        raise HTTPException(status_code=404, detail="Convite inválido, expirado ou já resolvido")
    return convite


@router.get("/{token}")
async def preview_convite(token: str, pool=Depends(get_pool)):
    """Sem autenticação — mostra pra quem clicou no link o que está
    aceitando ANTES de pedir login, sem vazar nada além do necessário
    (nome da Arena, papel, e-mail convidado)."""
    convite = await _resolver_convite_valido_ou_404(pool, token)
    arena = await arena_repo.buscar_por_id(pool, convite["arena_id"])
    return {
        "arena_nome": arena["nome"] if arena else None,
        "role": convite["role"],
        "email": convite["email"],
    }


@router.post("/{token}/aceitar")
async def aceitar_convite(
    token: str,
    pool=Depends(get_pool),
    usuario_auth: AuthenticatedUser = Depends(require_authenticated_user),
):
    """
    Exige sessão ativa cujo e-mail bate com o convidado (F.5) — mesma
    regra de account linking do AUTH_SPEC.md #2, aplicada aqui pra
    evitar sequestro de convite por link vazado pra terceiro: só o
    fato de estar logado não basta, precisa ser logado COM o e-mail
    certo.
    """
    convite = await _resolver_convite_valido_ou_404(pool, token)

    usuario = await auth_repo.buscar_usuario_por_id(pool, usuario_auth.user_id)
    if not usuario or auth_svc.normalizar_email(usuario.get("email") or "") != convite["email"]:
        raise HTTPException(
            status_code=403,
            detail=f"Este convite foi enviado para {convite['email']} — entre com essa conta pra aceitar.",
        )

    try:
        membership = await membership_repo.aceitar_convite(pool, convite["id"], usuario["id"])
    except Exception as exc:
        if "unique" in str(exc).lower():
            # Corrida rara: alguém já concedeu vínculo direto (POST
            # /api/admin/vinculos) pra esse user_id+arena enquanto o
            # convite ainda estava pendente — idx_memberships_unico
            # rejeita o UPDATE. A pessoa já tem acesso, então não é erro
            # de verdade pra quem está aceitando.
            raise HTTPException(status_code=409, detail="Você já tem acesso a esta Arena")
        raise
    if not membership:
        raise HTTPException(status_code=409, detail="Convite já foi aceito ou cancelado")

    await membership_repo.registrar_auditoria(
        pool, acao="convite_aceito", user_alvo_id=usuario["id"], realizado_por=usuario_auth.identificador,
        arena_id=convite["arena_id"], role=convite["role"],
    )
    return {"arena_id": convite["arena_id"], "role": convite["role"]}
