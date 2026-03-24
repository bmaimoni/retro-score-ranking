from asyncpg import Pool
from typing import Any


async def inserir(conn, dados: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO entradas
            (jogo_id, nick, nick_norm, pontuacao, foto_url,
             no_ranking, superado, pendente, ip_hash)
        VALUES ($1, $2, $3, $4, $5, $6, false, $7, $8)
        RETURNING id, jogo_id, nick, pontuacao, foto_url,
                  no_ranking, pendente, criado_em
        """,
        dados["jogo_id"],
        dados["nick"],
        dados["nick_norm"],
        dados["pontuacao"],
        dados["foto_url"],
        dados["no_ranking"],
        dados["pendente"],
        dados["ip_hash"],
    )
    return dict(row)


async def listar_ranking(pool: Pool, jogo_id: str) -> list[dict]:
    """
    Ranking público: apenas entradas visíveis, não superadas, não pendentes.
    Ordenadas por pontuação decrescente.
    Usa o índice parcial idx_ranking.
    """
    rows = await pool.fetch(
        """
        SELECT id, nick, pontuacao, foto_url, criado_em
        FROM entradas
        WHERE jogo_id    = $1
          AND no_ranking = true
          AND superado   = false
          AND pendente   = false
          AND arquivado  = false
        ORDER BY pontuacao DESC
        """,
        jogo_id,
    )
    return [dict(r) for r in rows]


async def listar_feed_admin(
    pool: Pool,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Feed do admin: todas as entradas, mais recentes primeiro."""
    rows = await pool.fetch(
        """
        SELECT e.id, e.nick, e.pontuacao, e.foto_url, e.no_ranking,
               e.superado, e.pendente, e.criado_em, e.moderado_em,
               e.moderado_por, j.nome AS jogo_nome, j.slug AS jogo_slug
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        ORDER BY e.criado_em DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )
    return [dict(r) for r in rows]


async def listar_pendentes(pool: Pool) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT e.id, e.nick, e.pontuacao, e.foto_url, e.criado_em,
               j.nome AS jogo_nome, j.slug AS jogo_slug
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        WHERE e.pendente = true
        ORDER BY e.criado_em ASC
        """,
    )
    return [dict(r) for r in rows]


async def atualizar_visibilidade(
    pool: Pool,
    entrada_id: str,
    no_ranking: bool,
    moderado_por: str,
) -> dict | None:
    row = await pool.fetchrow(
        """
        UPDATE entradas
        SET no_ranking   = $1,
            moderado_em  = now(),
            moderado_por = $2
        WHERE id = $3
        RETURNING id, jogo_id, nick, pontuacao, foto_url,
                  no_ranking, pendente, superado, criado_em
        """,
        no_ranking, moderado_por, entrada_id,
    )
    return dict(row) if row else None


async def resolver_pendente(
    pool: Pool,
    entrada_id: str,
    aprovar: bool,
    moderado_por: str,
) -> dict | None:
    """
    Aprova (pendente=false, no_ranking=true) ou
    oculta (pendente=false, no_ranking=false) uma entrada pendente.
    """
    row = await pool.fetchrow(
        """
        UPDATE entradas
        SET pendente     = false,
            no_ranking   = $1,
            moderado_em  = now(),
            moderado_por = $2
        WHERE id      = $3
          AND pendente = true
        RETURNING id, jogo_id, nick, pontuacao, foto_url,
                  no_ranking, pendente, superado, criado_em
        """,
        aprovar, moderado_por, entrada_id,
    )
    return dict(row) if row else None


async def buscar_por_id(pool: Pool, entrada_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT e.*, j.slug AS jogo_slug
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        WHERE e.id = $1
        """,
        entrada_id,
    )
    return dict(row) if row else None