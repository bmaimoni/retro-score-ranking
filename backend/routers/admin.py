from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, UUID4
from middleware.auth import require_admin
from utils.db import get_pool
from services.sse import broker
import repositories.entrada as entrada_repo
import repositories.jogo as jogo_repo
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class AtualizarVisibilidade(BaseModel):
    no_ranking: bool

class ResolverPendente(BaseModel):
    aprovar: bool

class CriarJogo(BaseModel):
    nome: str
    slug: str
    score_max: int | None = None

class AtualizarJogo(BaseModel):
    ativo: bool | None = None
    score_max: int | None = None


# ── FEED ──────────────────────────────────────────────────────────────────────

@router.get("/feed")
async def feed_entradas(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Feed de todas as entradas recentes, incluindo ocultas e pendentes."""
    return await entrada_repo.listar_feed_admin(pool, limit=limit, offset=offset)


@router.get("/pendentes")
async def listar_pendentes(
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Entradas aguardando decisão do moderador (vieram pelo rate limit)."""
    return await entrada_repo.listar_pendentes(pool)


# ── MODERAÇÃO DE ENTRADAS ─────────────────────────────────────────────────────

@router.patch("/entradas/{entrada_id}")
async def moderar_entrada(
    entrada_id: UUID4,
    body: AtualizarVisibilidade,
    pool=Depends(get_pool),
    moderador: str = Depends(require_admin),
):
    """
    Oculta (no_ranking=false) ou reativa (no_ranking=true) uma entrada.
    A foto nunca é deletada — evidência sempre preservada.
    Emite evento SSE para os clientes do ranking.
    """
    entrada = await entrada_repo.atualizar_visibilidade(
        pool, str(entrada_id), body.no_ranking, moderador
    )
    if not entrada:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")

    # Busca o slug para o SSE
    row = await pool.fetchrow("SELECT slug FROM jogos WHERE id = $1", entrada["jogo_id"])
    slug = row["slug"] if row else str(entrada["jogo_id"])

    if body.no_ranking:
        await broker.publish(slug, "reativar", {
            "id": str(entrada_id),
            "entrada": {
                "id":        str(entrada["id"]),
                "nick":      entrada["nick"],
                "pontuacao": entrada["pontuacao"],
                "foto_url":  entrada["foto_url"],
            }
        })
    else:
        await broker.publish(slug, "ocultar", {"id": str(entrada_id)})

    log.info(
        "moderacao",
        entrada_id=str(entrada_id),
        no_ranking=body.no_ranking,
        moderador=moderador,
    )

    return entrada


@router.patch("/entradas/{entrada_id}/pendente")
async def resolver_pendente(
    entrada_id: UUID4,
    body: ResolverPendente,
    pool=Depends(get_pool),
    moderador: str = Depends(require_admin),
):
    """
    Resolve uma entrada pendente:
    - aprovar=true  → pendente=false, no_ranking=true  (aparece no ranking)
    - aprovar=false → pendente=false, no_ranking=false (fica oculta)
    """
    entrada = await entrada_repo.resolver_pendente(
        pool, str(entrada_id), body.aprovar, moderador
    )
    if not entrada:
        raise HTTPException(
            status_code=404,
            detail="Entrada não encontrada ou não está pendente",
        )

    if body.aprovar:
        row = await pool.fetchrow("SELECT slug FROM jogos WHERE id = $1", entrada["jogo_id"])
        slug = row["slug"] if row else str(entrada["jogo_id"])
        await broker.publish(slug, "novo_registro", {
            "id":        str(entrada["id"]),
            "nick":      entrada["nick"],
            "pontuacao": entrada["pontuacao"],
            "foto_url":  entrada["foto_url"],
            "criado_em": str(entrada["criado_em"]),
        })

    log.info(
        "pendente_resolvido",
        entrada_id=str(entrada_id),
        aprovado=body.aprovar,
        moderador=moderador,
    )

    return entrada


# ── GESTÃO DE JOGOS ───────────────────────────────────────────────────────────

@router.post("/jogos", status_code=201)
async def criar_jogo(
    body: CriarJogo,
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Cria um novo jogo para o evento."""
    try:
        return await jogo_repo.criar(pool, body.nome, body.slug, body.score_max)
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail=f"Slug '{body.slug}' já existe")
        raise HTTPException(status_code=500, detail="Erro ao criar jogo")


@router.patch("/jogos/{jogo_id}")
async def atualizar_jogo(
    jogo_id: UUID4,
    body: AtualizarJogo,
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Ativa/desativa um jogo ou atualiza seu score_max."""
    jogo = await jogo_repo.atualizar(pool, str(jogo_id), body.ativo, body.score_max)
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado ou nada para atualizar")
    return jogo

@router.get("/jogos-todos")
async def listar_jogos_todos(
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Lista todos os jogos incluindo inativos — para o painel admin."""
    return await jogo_repo.listar_todos(pool)


# ── CONFIGURAÇÃO DO EVENTO ────────────────────────────────────────────────────

import repositories.evento_config as config_repo

class AtualizarConfig(BaseModel):
    valor: str

@router.get("/config")
async def listar_config(
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Lista todas as configurações do evento."""
    return await config_repo.listar(pool)


@router.patch("/config/{chave}")
async def atualizar_config(
    chave: str,
    body: AtualizarConfig,
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Atualiza uma configuração pelo nome da chave."""
    cfg = await config_repo.atualizar(pool, chave, body.valor)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Configuração '{chave}' não encontrada")
    return cfg


# ── MANUTENÇÃO DE RANKINGS ────────────────────────────────────────────────────

class LimparRankingBody(BaseModel):
    jogo_id: str | None = None        # None = todos os jogos
    permanente: bool = False           # False = soft delete, True = DELETE físico
    confirmar: str = ""               # deve ser "CONFIRMAR" para prosseguir


@router.post("/manutencao/limpar-ranking")
async def limpar_ranking(
    body: LimparRankingBody,
    pool=Depends(get_pool),
    moderador: str = Depends(require_admin),
):
    """
    Limpa entradas de um jogo ou de todos os jogos.
    - permanente=False → soft delete (arquivado=true), reversível
    - permanente=True  → DELETE físico, irreversível
    Exige confirmar="CONFIRMAR" para prosseguir.
    """
    if body.confirmar != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Envie confirmar='CONFIRMAR' para prosseguir")

    if body.permanente:
        if body.jogo_id:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entradas WHERE jogo_id = $1", body.jogo_id
            )
            await pool.execute("DELETE FROM entradas WHERE jogo_id = $1", body.jogo_id)
        else:
            count = await pool.fetchval("SELECT COUNT(*) FROM entradas")
            await pool.execute("DELETE FROM entradas")
        log.warning("ranking_limpo_permanente", jogo_id=body.jogo_id, total=count, moderador=moderador)
    else:
        if body.jogo_id:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entradas WHERE jogo_id = $1 AND arquivado = false",
                body.jogo_id
            )
            await pool.execute(
                """UPDATE entradas SET arquivado = true, arquivado_em = now(), arquivado_por = $1
                   WHERE jogo_id = $2 AND arquivado = false""",
                moderador, body.jogo_id
            )
        else:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entradas WHERE arquivado = false"
            )
            await pool.execute(
                """UPDATE entradas SET arquivado = true, arquivado_em = now(), arquivado_por = $1
                   WHERE arquivado = false""",
                moderador
            )
        log.warning("ranking_arquivado", jogo_id=body.jogo_id, total=count, moderador=moderador)

    return {"ok": True, "total_afetadas": count, "permanente": body.permanente}


@router.post("/manutencao/restaurar-ranking")
async def restaurar_ranking(
    body: LimparRankingBody,
    pool=Depends(get_pool),
    moderador: str = Depends(require_admin),
):
    """Restaura entradas arquivadas de um jogo ou de todos."""
    if body.confirmar != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Envie confirmar='CONFIRMAR' para prosseguir")

    if body.jogo_id:
        count = await pool.fetchval(
            "SELECT COUNT(*) FROM entradas WHERE jogo_id = $1 AND arquivado = true",
            body.jogo_id
        )
        await pool.execute(
            "UPDATE entradas SET arquivado = false, arquivado_em = null, arquivado_por = null WHERE jogo_id = $1 AND arquivado = true",
            body.jogo_id
        )
    else:
        count = await pool.fetchval("SELECT COUNT(*) FROM entradas WHERE arquivado = true")
        await pool.execute(
            "UPDATE entradas SET arquivado = false, arquivado_em = null, arquivado_por = null WHERE arquivado = true"
        )

    log.info("ranking_restaurado", jogo_id=body.jogo_id, total=count, moderador=moderador)
    return {"ok": True, "total_restauradas": count}