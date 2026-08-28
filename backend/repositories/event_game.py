from asyncpg import Pool


async def listar_por_event(pool: Pool, event_id: str) -> list[dict]:
    """Jogos ativos de um evento, ordenados pelo campo ordem."""
    rows = await pool.fetch(
        """
        SELECT
            j.id, j.nome, j.slug, j.score_max,
            ej.ativo, ej.ordem
        FROM event_games ej
        JOIN games j ON j.id = ej.game_id
        WHERE ej.event_id = $1
          AND ej.ativo     = true
          AND j.ativo      = true
        ORDER BY ej.ordem, j.nome
        """,
        event_id,
    )
    return [dict(r) for r in rows]


async def adicionar(pool: Pool, event_id: str, game_id: str, ordem: int = 0) -> dict:
    """Adiciona game ao event. Se já existir, reativa e atualiza ordem."""
    row = await pool.fetchrow(
        """
        INSERT INTO event_games (event_id, game_id, ordem)
        VALUES ($1, $2, $3)
        ON CONFLICT (event_id, game_id)
        DO UPDATE SET ativo = true, ordem = EXCLUDED.ordem
        RETURNING id, event_id, game_id, ativo, ordem, criado_em
        """,
        event_id, game_id, ordem,
    )
    return dict(row)


async def atualizar(pool: Pool, event_id: str, game_id: str, dados: dict) -> dict | None:
    """Atualiza ativo e/ou ordem de um game num event."""
    row = await pool.fetchrow(
        """
        UPDATE event_games
        SET ativo = COALESCE($3, ativo),
            ordem = COALESCE($4, ordem)
        WHERE event_id = $1
          AND game_id   = $2
        RETURNING id, event_id, game_id, ativo, ordem, criado_em
        """,
        event_id, game_id,
        dados.get("ativo"),
        dados.get("ordem"),
    )
    return dict(row) if row else None
