from asyncpg import Pool


async def buscar_por_slug(pool: Pool, slug: str) -> dict | None:
    """Busca placar pelo slug. Retorna None se não existir."""
    row = await pool.fetchrow(
        "SELECT id, nome, slug, escopo FROM placares WHERE slug = $1",
        slug,
    )
    return dict(row) if row else None


async def listar_ranking(pool: Pool, jogo_id: str, placar: dict) -> list[dict]:
    """
    Ranking de um jogo dentro do escopo do placar:
      - escopo='global'      → todos os eventos (presentes e futuros), sem filtro
      - escopo='customizado' → só eventos vinculados via placar_eventos

    Mesmo desempate dos demais rankings (criado_em ASC, id ASC) — ver
    docs/EVENTOS_SPEC.md §4.2.
    """
    if placar["escopo"] == "global":
        rows = await pool.fetch(
            """
            SELECT id, nick, nome, pontuacao, foto_url, evento_id, criado_em
            FROM entradas
            WHERE jogo_id    = $1
              AND no_ranking = true
              AND superado   = false
              AND pendente   = false
              AND arquivado  = false
            ORDER BY pontuacao DESC, criado_em ASC, id ASC
            """,
            jogo_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, nick, nome, pontuacao, foto_url, evento_id, criado_em
            FROM entradas
            WHERE jogo_id    = $1
              AND evento_id IN (SELECT evento_id FROM placar_eventos WHERE placar_id = $2)
              AND no_ranking = true
              AND superado   = false
              AND pendente   = false
              AND arquivado  = false
            ORDER BY pontuacao DESC, criado_em ASC, id ASC
            """,
            jogo_id, placar["id"],
        )
    return [dict(r) for r in rows]


async def listar_lideres(pool: Pool, placar: dict) -> dict:
    """Top 1 de cada jogo ativo, dentro do escopo do placar."""
    if placar["escopo"] == "global":
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (e.jogo_id)
                e.jogo_id, j.slug, e.nick, e.pontuacao
            FROM entradas e
            JOIN jogos j ON j.id = e.jogo_id
            WHERE e.no_ranking = true
              AND e.superado   = false
              AND e.pendente   = false
              AND e.arquivado  = false
              AND j.ativo      = true
            ORDER BY e.jogo_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC
            """
        )
    else:
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (e.jogo_id)
                e.jogo_id, j.slug, e.nick, e.pontuacao
            FROM entradas e
            JOIN jogos j ON j.id = e.jogo_id
            WHERE e.evento_id IN (SELECT evento_id FROM placar_eventos WHERE placar_id = $1)
              AND e.no_ranking = true
              AND e.superado   = false
              AND e.pendente   = false
              AND e.arquivado  = false
              AND j.ativo      = true
            ORDER BY e.jogo_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC
            """,
            placar["id"],
        )
    return {
        str(r["jogo_id"]): {"slug": r["slug"], "nick": r["nick"], "pontuacao": r["pontuacao"]}
        for r in rows
    }
