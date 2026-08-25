"""
Router de perfil de usuário — requer login (sessão de visitante comum,
não admin). Prefixo: /api/perfil

Ver docs/BACKLOG_2026.md §1 (itens 1.3/1.4/1.5/1.7/1.8), docs/EXCLUSAO_CONTA_SPEC.md
e docs/SEGUIR_SPEC.md.
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from utils.db import get_pool
import auth.service as auth_svc
import auth.repository as auth_repo
import repositories.usuario as usuario_repo
import repositories.avatar as avatar_repo
import repositories.entrada as entrada_repo
import repositories.seguidor as seguidor_repo
import services.exclusao_conta as exclusao_svc

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


# ── Minhas pontuações (BACKLOG_2026.md item 1.4) ────────────────────────────────

@router.get("/pontuacoes")
async def minhas_pontuacoes(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    """Detalhamento de todas as próprias pontuações — jogo, evento e
    marca de cada uma, pra tela de perfil linkar direto pro jogo."""
    return await entrada_repo.listar_por_usuario(pool, usuario["id"])


# ── Desativar pontuações — leve, reversível (BACKLOG_2026.md item 1.5) ─────────

@router.post("/desativar-pontuacoes")
async def desativar_pontuacoes(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    """
    Arquiva (soft) todas as pontuações do usuário — reversível, não
    mexe em dado pessoal. Distinto de excluir conta: nunca no mesmo
    botão/fluxo (decisão #4 do docs/EXCLUSAO_CONTA_SPEC.md §4).
    """
    total = await usuario_repo.desativar_pontuacoes(pool, usuario["id"], usuario.get("email") or usuario["id"])
    return {"ok": True, "total_afetadas": total}


# ── Exclusão de conta — pesada, com janela de cancelamento (EXCLUSAO_CONTA_SPEC.md) ─

@router.post("/exclusao", status_code=201)
async def solicitar_exclusao(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    """
    Inicia a janela de 30 dias de cancelamento — a conta continua
    normal até lá. Bloqueado na hora se a pessoa for titular de
    qualquer marca (decisão #5).
    """
    try:
        return await exclusao_svc.solicitar(pool, usuario["id"])
    except exclusao_svc.ExclusaoBloqueadaTitularidadeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/exclusao/cancelar")
async def cancelar_exclusao(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    """Desiste da exclusão dentro da janela de 30 dias (decisão #2)."""
    resultado = await exclusao_svc.cancelar(pool, usuario["id"])
    if not resultado:
        raise HTTPException(status_code=404, detail="Não há solicitação de exclusão pendente")
    return resultado


# ── Seguir jogadores (docs/SEGUIR_SPEC.md) ──────────────────────────────────────

@router.post("/seguir/{user_id}", status_code=201)
async def seguir(
    user_id: str,
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    if user_id == usuario["id"]:
        raise HTTPException(status_code=422, detail="Não é possível seguir a própria conta")
    try:
        return await seguidor_repo.seguir(pool, usuario["id"], user_id)
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        raise


@router.post("/seguir/{user_id}/cancelar")
async def deixar_de_seguir(
    user_id: str,
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    resultado = await seguidor_repo.deixar_de_seguir(pool, usuario["id"], user_id)
    if not resultado:
        raise HTTPException(status_code=404, detail="Você não segue este usuário")
    return resultado


@router.get("/seguindo")
async def listar_seguindo(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    return await seguidor_repo.listar_seguindo(pool, usuario["id"])


@router.get("/seguidores")
async def listar_seguidores(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    return await seguidor_repo.listar_seguidores(pool, usuario["id"])


@router.get("/atividade")
async def minha_atividade(
    pool=Depends(get_pool),
    usuario: dict = Depends(auth_svc.sessao_obrigatoria),
):
    """
    Feed de superação de score entre quem eu sigo, compilado agora
    (decisão #5 do SEGUIR_SPEC.md — não a cada envio de score). Marca
    como conferido ao final: users.ultimo_login_em avança pra agora,
    então a próxima chamada só traz o que aconteceu depois desta
    (decisão #6 — sem repetir o que já foi mostrado).
    """
    desde = usuario.get("ultimo_login_em")
    atividade = await seguidor_repo.compilar_atividade(pool, usuario["id"], desde)
    await auth_repo.atualizar_ultimo_login(pool, usuario["id"])
    return atividade
