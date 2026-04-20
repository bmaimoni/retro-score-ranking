"""
Router público de eventos — acessível sem autenticação.
Prefixo: /api/e/{slug}

Endpoints:
  GET /api/e/{slug}/config        → config pública do evento
  GET /api/e/{slug}/jogos         → jogos ativos do evento
  GET /api/e/{slug}/ranking/{jogo_slug} → ranking filtrado por evento
"""
from fastapi import APIRouter, Depends, HTTPException
from utils.db import get_pool
import repositories.evento      as evento_repo
import repositories.evento_jogo as evento_jogo_repo
import repositories.jogo        as jogo_repo
import repositories.entrada     as entrada_repo

router = APIRouter(prefix="/api/e", tags=["evento-publico"])


async def _get_evento_publico(slug: str, pool) -> dict:
    """Helper: busca evento público ou levanta 404/403."""
    evento = await evento_repo.buscar_por_slug(pool, slug)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    if not evento["ativo"]:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    if not evento["publico"]:
        raise HTTPException(status_code=403, detail="Este evento está temporariamente inacessível")
    return evento


# ── Config pública do evento ──────────────────────────────────

@router.get("/{slug}/config")
async def get_config_evento(slug: str, pool=Depends(get_pool)):
    """
    Retorna configuração pública do evento:
    nome, logo_url, cor_primaria.
    Usado pelo frontend para aplicar identidade visual.
    """
    evento = await _get_evento_publico(slug, pool)
    return {
        "slug":         evento["slug"],
        "nome":         evento["nome"],
        "logo_url":     evento.get("logo_url"),
        "cor_primaria": evento.get("cor_primaria"),
    }


# ── Jogos do evento ───────────────────────────────────────────

@router.get("/{slug}/jogos")
async def get_jogos_evento(slug: str, pool=Depends(get_pool)):
    """
    Lista jogos ativos do evento, com seus temas.
    Substitui /api/jogos no contexto de um evento específico.
    """
    evento = await _get_evento_publico(slug, pool)
    jogos  = await evento_jogo_repo.listar_por_evento(pool, str(evento["id"]))
    return jogos


# ── Ranking filtrado por evento ───────────────────────────────

@router.get("/{slug}/ranking/{jogo_slug}")
async def get_ranking_evento(slug: str, jogo_slug: str, pool=Depends(get_pool)):
    """
    Ranking de um jogo filtrado pelo evento.
    Retorna apenas scores registrados neste evento.
    """
    evento = await _get_evento_publico(slug, pool)
    jogo   = await jogo_repo.buscar_por_slug(pool, jogo_slug)
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    entradas = await entrada_repo.listar_ranking_por_evento(
        pool, str(jogo["id"]), str(evento["id"])
    )
    return {"jogo": jogo, "evento": slug, "entradas": entradas}


# ── Líderes por evento ────────────────────────────────────────

@router.get("/{slug}/ranking/lideres")
async def get_lideres_evento(slug: str, pool=Depends(get_pool)):
    """
    Top 1 de cada jogo do evento.
    Usado no index para exibir o líder em cada card de jogo.
    """
    evento = await _get_evento_publico(slug, pool)
    rows   = await pool.fetch(
        """
        SELECT DISTINCT ON (e.jogo_id)
            e.jogo_id,
            j.slug,
            e.nick,
            e.pontuacao
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        JOIN evento_jogos ej ON ej.jogo_id = e.jogo_id
                             AND ej.evento_id = $1
                             AND ej.ativo = true
        WHERE e.evento_id  = $1
          AND e.no_ranking = true
          AND e.superado   = false
          AND e.pendente   = false
          AND e.arquivado  = false
        ORDER BY e.jogo_id, e.pontuacao DESC
        """,
        str(evento["id"]),
    )
    return {
        str(r["jogo_id"]): {
            "slug":      r["slug"],
            "nick":      r["nick"],
            "pontuacao": r["pontuacao"],
        }
        for r in rows
    }
