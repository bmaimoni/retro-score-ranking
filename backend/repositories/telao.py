from asyncpg import Pool


async def buscar_config_por_slug(pool: Pool, slug: str) -> dict | None:
    """
    Config pública de um telão: nome, top_n (posições fixas exibidas, sem
    paginação — ver docs/EVENTOS_SPEC.md §5), o evento ou placar ao qual
    aponta, e os jogos do carrossel já ordenados.
    """
    telao = await pool.fetchrow(
        """
        SELECT t.id, t.nome, t.slug, t.top_n,
               t.evento_id, e.slug AS evento_slug,
               t.placar_id, p.slug AS placar_slug
        FROM teloes t
        LEFT JOIN eventos  e ON e.id = t.evento_id
        LEFT JOIN placares p ON p.id = t.placar_id
        WHERE t.slug = $1
        """,
        slug,
    )
    if not telao:
        return None

    jogos = await pool.fetch(
        """
        SELECT j.nome, j.slug, tj.ordem
        FROM telao_jogos tj
        JOIN jogos j ON j.id = tj.jogo_id
        WHERE tj.telao_id = $1
          AND tj.ativo    = true
        ORDER BY tj.ordem
        """,
        telao["id"],
    )

    return {
        "nome":        telao["nome"],
        "slug":        telao["slug"],
        "top_n":       telao["top_n"],
        "evento_slug": telao["evento_slug"],
        "placar_slug": telao["placar_slug"],
        "jogos":       [dict(j) for j in jogos],
    }
