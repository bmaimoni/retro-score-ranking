from asyncpg import Pool


async def listar(pool: Pool) -> list[dict]:
    """Todos os eventos, mais recentes primeiro."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, ativo, data_inicio, data_fim, criado_em
        FROM eventos
        ORDER BY criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def listar_ativos(pool: Pool) -> list[dict]:
    """Eventos ativos, ordenados por criado_em DESC."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, ativo, data_inicio, data_fim, criado_em
        FROM eventos
        WHERE ativo = true
        ORDER BY criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def buscar_ativo_mais_recente(pool: Pool) -> dict | None:
    """Retorna o evento ativo mais recente — usado no upload."""
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug
        FROM eventos
        WHERE ativo = true
        ORDER BY criado_em DESC
        LIMIT 1
        """
    )
    return dict(row) if row else None


async def buscar_por_slug(pool: Pool, slug: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT id, nome, slug, ativo, data_inicio, data_fim, criado_em FROM eventos WHERE slug = $1",
        slug,
    )
    return dict(row) if row else None


async def criar(pool: Pool, dados: dict) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO eventos (nome, slug, ativo, data_inicio, data_fim)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, nome, slug, ativo, data_inicio, data_fim, criado_em
        """,
        dados["nome"],
        dados["slug"],
        dados.get("ativo", True),
        dados.get("data_inicio"),
        dados.get("data_fim"),
    )
    return dict(row)


async def atualizar(pool: Pool, evento_id: str, dados: dict) -> dict | None:
    row = await pool.fetchrow(
        """
        UPDATE eventos
        SET nome        = COALESCE($2, nome),
            ativo       = COALESCE($3, ativo),
            data_inicio = COALESCE($4, data_inicio),
            data_fim    = COALESCE($5, data_fim)
        WHERE id = $1
        RETURNING id, nome, slug, ativo, data_inicio, data_fim, criado_em
        """,
        evento_id,
        dados.get("nome"),
        dados.get("ativo"),
        dados.get("data_inicio"),
        dados.get("data_fim"),
    )
    return dict(row) if row else None
