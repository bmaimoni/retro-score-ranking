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


# ── Admin: CRUD de telões ──────────────────────────────────────

async def listar_todos(pool: Pool) -> list[dict]:
    """Todos os telões — para o painel admin."""
    rows = await pool.fetch(
        """
        SELECT t.id, t.nome, t.slug, t.top_n,
               t.evento_id, e.slug AS evento_slug,
               t.placar_id, p.slug AS placar_slug,
               t.criado_em
        FROM teloes t
        LEFT JOIN eventos  e ON e.id = t.evento_id
        LEFT JOIN placares p ON p.id = t.placar_id
        ORDER BY t.criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def buscar_por_id(pool: Pool, telao_id: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT id, nome, slug, top_n, evento_id, placar_id, criado_em FROM teloes WHERE id = $1",
        telao_id,
    )
    return dict(row) if row else None


async def criar(
    pool: Pool,
    nome: str,
    slug: str,
    top_n: int = 10,
    evento_id: str | None = None,
    placar_id: str | None = None,
) -> dict:
    """
    Cria um telão. Exatamente um entre evento_id/placar_id deve ser
    informado — o CHECK teloes_evento_ou_placar garante isso no banco
    (ver migration 011).
    """
    row = await pool.fetchrow(
        """
        INSERT INTO teloes (nome, slug, top_n, evento_id, placar_id)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, nome, slug, top_n, evento_id, placar_id, criado_em
        """,
        nome, slug, top_n, evento_id, placar_id,
    )
    return dict(row)


async def atualizar(pool: Pool, telao_id: str, dados: dict) -> dict | None:
    """Atualiza nome e/ou top_n de um telão. evento_id/placar_id são imutáveis
    após criação — trocar o escopo de um telão é criar um novo."""
    row = await pool.fetchrow(
        """
        UPDATE teloes
        SET nome  = COALESCE($2, nome),
            top_n = COALESCE($3, top_n)
        WHERE id = $1
        RETURNING id, nome, slug, top_n, evento_id, placar_id, criado_em
        """,
        telao_id,
        dados.get("nome"),
        dados.get("top_n"),
    )
    return dict(row) if row else None


# ── Admin: gestão de telao_jogos ────────────────────────────────

async def listar_jogos_do_telao(pool: Pool, telao_id: str) -> list[dict]:
    """Jogos vinculados ao telão (ativos e inativos) — para o painel admin."""
    rows = await pool.fetch(
        """
        SELECT j.id, j.nome, j.slug, tj.ativo, tj.ordem
        FROM telao_jogos tj
        JOIN jogos j ON j.id = tj.jogo_id
        WHERE tj.telao_id = $1
        ORDER BY tj.ordem, j.nome
        """,
        telao_id,
    )
    return [dict(r) for r in rows]


async def adicionar_jogo(pool: Pool, telao_id: str, jogo_id: str, ordem: int = 0) -> dict:
    """Adiciona jogo ao telão. Se já existir, reativa e atualiza ordem."""
    row = await pool.fetchrow(
        """
        INSERT INTO telao_jogos (telao_id, jogo_id, ordem)
        VALUES ($1, $2, $3)
        ON CONFLICT (telao_id, jogo_id)
        DO UPDATE SET ativo = true, ordem = EXCLUDED.ordem
        RETURNING telao_id, jogo_id, ativo, ordem, criado_em
        """,
        telao_id, jogo_id, ordem,
    )
    return dict(row)


async def atualizar_jogo(pool: Pool, telao_id: str, jogo_id: str, dados: dict) -> dict | None:
    """Atualiza ativo e/ou ordem de um jogo num telão."""
    row = await pool.fetchrow(
        """
        UPDATE telao_jogos
        SET ativo = COALESCE($3, ativo),
            ordem = COALESCE($4, ordem)
        WHERE telao_id = $1
          AND jogo_id  = $2
        RETURNING telao_id, jogo_id, ativo, ordem, criado_em
        """,
        telao_id, jogo_id,
        dados.get("ativo"),
        dados.get("ordem"),
    )
    return dict(row) if row else None
