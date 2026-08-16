"""
Router público de placares — acessível sem autenticação.
Prefixo: /api/p/{slug}

Endpoints:
  GET /api/p/{slug}/ranking/lideres      → top 1 de cada jogo, no escopo do placar
  GET /api/p/{slug}/ranking/{jogo_slug}  → ranking de um jogo, no escopo do placar

Ver docs/EVENTOS_SPEC.md §3-4 para o desenho completo (placar global
seedado por migração + placares customizados curados pelo admin).
"""
from fastapi import APIRouter, Depends, HTTPException
from utils.db import get_pool
import repositories.placar as placar_repo
import repositories.jogo   as jogo_repo

router = APIRouter(prefix="/api/p", tags=["placar-publico"])


async def _get_placar(slug: str, pool) -> dict:
    """Helper: busca placar ou levanta 404."""
    placar = await placar_repo.buscar_por_slug(pool, slug)
    if not placar:
        raise HTTPException(status_code=404, detail="Placar não encontrado")
    return placar


# ── Líderes do placar ─────────────────────────────────────────
# IMPORTANTE: esta rota deve vir ANTES de /{slug}/ranking/{jogo_slug},
# senão "lideres" é capturado como jogo_slug pela rota genérica
# (mesma armadilha já documentada em SPEC.md §8 e evento_publico.py).

@router.get("/{slug}/ranking/lideres")
async def get_lideres_placar(slug: str, pool=Depends(get_pool)):
    """Top 1 de cada jogo ativo, dentro do escopo do placar."""
    placar = await _get_placar(slug, pool)
    return await placar_repo.listar_lideres(pool, placar)


# ── Ranking do placar ─────────────────────────────────────────

@router.get("/{slug}/ranking/{jogo_slug}")
async def get_ranking_placar(slug: str, jogo_slug: str, pool=Depends(get_pool)):
    """
    Ranking de um jogo dentro do escopo do placar (global ou customizado).
    """
    placar = await _get_placar(slug, pool)
    jogo   = await jogo_repo.buscar_por_slug(pool, jogo_slug)
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    entradas = await placar_repo.listar_ranking(pool, str(jogo["id"]), placar)
    return {"jogo": jogo, "placar": slug, "entradas": entradas}
