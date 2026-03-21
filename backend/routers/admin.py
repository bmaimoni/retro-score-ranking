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
