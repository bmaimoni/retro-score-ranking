from asyncpg import Pool


async def listar_por_evento(pool: Pool, evento_id: str) -> list[dict]:
    """Jogos ativos de um evento, ordenados pelo campo ordem."""
    rows = await pool.fetch(
        """
        SELECT
            j.id, j.nome, j.slug, j.score_max,
            ej.ativo, ej.ordem
        FROM evento_jogos ej
        JOIN jogos j ON j.id = ej.jogo_id
        WHERE ej.evento_id = $1
          AND ej.ativo     = true
          AND j.ativo      = true
        ORDER BY ej.ordem, j.nome
        """,
        evento_id,
    )
    return [dict(r) for r in rows]


async def adicionar(pool: Pool, evento_id: str, jogo_id: str, ordem: int = 0) -> dict:
    """Adiciona jogo ao evento. Se já existir, reativa e atualiza ordem."""
    row = await pool.fetchrow(
        """
        INSERT INTO evento_jogos (evento_id, jogo_id, ordem)
        VALUES ($1, $2, $3)
        ON CONFLICT (evento_id, jogo_id)
        DO UPDATE SET ativo = true, ordem = EXCLUDED.ordem
        RETURNING id, evento_id, jogo_id, ativo, ordem, criado_em
        """,
        evento_id, jogo_id, ordem,
    )
    return dict(row)


async def atualizar(pool: Pool, evento_id: str, jogo_id: str, dados: dict) -> dict | None:
    """Atualiza ativo e/ou ordem de um jogo num evento."""
    row = await pool.fetchrow(
        """
        UPDATE evento_jogos
        SET ativo = COALESCE($3, ativo),
            ordem = COALESCE($4, ordem)
        WHERE evento_id = $1
          AND jogo_id   = $2
        RETURNING id, evento_id, jogo_id, ativo, ordem, criado_em
        """,
        evento_id, jogo_id,
        dados.get("ativo"),
        dados.get("ordem"),
    )
    return dict(row) if row else None
