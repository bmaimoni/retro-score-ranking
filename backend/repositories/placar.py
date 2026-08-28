from asyncpg import Pool


async def buscar_por_slug(pool: Pool, slug: str) -> dict | None:
    """Busca placar pelo slug. Retorna None se não existir."""
    row = await pool.fetchrow(
        "SELECT id, nome, slug, escopo, criado_em FROM placares WHERE slug = $1",
        slug,
    )
    return dict(row) if row else None


async def buscar_por_id(pool: Pool, placar_id: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT id, nome, slug, escopo, criado_em FROM placares WHERE id = $1",
        placar_id,
    )
    return dict(row) if row else None


async def listar_todos(pool: Pool) -> list[dict]:
    """Todos os placares — para o painel admin."""
    rows = await pool.fetch(
        "SELECT id, nome, slug, escopo, criado_em FROM placares ORDER BY criado_em DESC"
    )
    return [dict(r) for r in rows]


async def criar(pool: Pool, nome: str, slug: str) -> dict:
    """
    Cria um placar customizado. O placar global é único e seedado por
    migração — não é criado via este endpoint (ver EVENTOS_SPEC.md §3,
    índice único parcial idx_placares_unico_global impede um segundo).
    """
    row = await pool.fetchrow(
        """
        INSERT INTO placares (nome, slug, escopo)
        VALUES ($1, $2, 'customizado')
        RETURNING id, nome, slug, escopo, criado_em
        """,
        nome, slug,
    )
    return dict(row)


async def resolver_arena_id(pool: Pool, placar_id: str) -> str | None:
    """
    Arena 'efetiva' de um placar customizado, SE todos os events
    vinculados (placar_eventos) pertencerem à mesma arena — caso comum
    de uso real (ex: Hall da Fama só com events da Canal3). Se os
    events vinculados forem de arenas diferentes, ou não houver nenhum
    ainda, retorna None. O placar 'global' também sempre retorna None
    aqui — não usa placar_eventos (agrega tudo, sem filtro), não
    pertence a nenhuma arena.

    None é tratado por quem chama como "só super pode operar" — ver
    routers/teloes_admin.py. Não existe hoje um jeito de um admin de
    arena "reivindicar" um placar customizado multi-arena; é decisão
    consciente de simplificação, não suportada ainda pelo schema
    (placares não tem arena_id próprio).
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT e.arena_id
        FROM placar_eventos pe
        JOIN events e ON e.id = pe.evento_id
        WHERE pe.placar_id = $1
        """,
        placar_id,
    )
    if len(rows) != 1:
        return None
    return str(rows[0]["arena_id"])


async def listar_events_do_placar(pool: Pool, placar_id: str) -> list[dict]:
    """Eventos vinculados a um placar customizado (ativos e inativos)."""
    rows = await pool.fetch(
        """
        SELECT e.id, e.nome, e.slug, pe.ativo, pe.criado_em
        FROM placar_eventos pe
        JOIN events e ON e.id = pe.evento_id
        WHERE pe.placar_id = $1
        ORDER BY pe.criado_em DESC
        """,
        placar_id,
    )
    return [dict(r) for r in rows]


async def adicionar_event(pool: Pool, placar_id: str, event_id: str) -> dict:
    """Vincula um event ao placar. Se já existir (mesmo inativo), reativa."""
    row = await pool.fetchrow(
        """
        INSERT INTO placar_eventos (placar_id, evento_id)
        VALUES ($1, $2)
        ON CONFLICT (placar_id, evento_id)
        DO UPDATE SET ativo = true
        RETURNING placar_id, evento_id, ativo, criado_em
        """,
        placar_id, event_id,
    )
    return dict(row)


async def remover_event(pool: Pool, placar_id: str, event_id: str) -> dict | None:
    """
    Remove um event do placar (soft — ativo=false, sem DELETE físico).
    app_user não tem permissão de DELETE em placar_eventos.
    """
    row = await pool.fetchrow(
        """
        UPDATE placar_eventos
        SET ativo = false
        WHERE placar_id = $1 AND evento_id = $2
        RETURNING placar_id, evento_id, ativo, criado_em
        """,
        placar_id, event_id,
    )
    return dict(row) if row else None


async def listar_ranking(pool: Pool, game_id: str, placar: dict) -> list[dict]:
    """
    Ranking de um game dentro do escopo do placar:
      - escopo='global'      → todos os events (presentes e futuros), sem filtro
      - escopo='customizado' → só events vinculados via placar_eventos

    Mesmo desempate dos demais rankings (criado_em ASC, id ASC) — ver
    docs/EVENTOS_SPEC.md §4.2.
    """
    if placar["escopo"] == "global":
        rows = await pool.fetch(
            """
            SELECT e.id, e.nick, e.nome, e.pontuacao, e.foto_url, e.event_id, e.criado_em
            FROM entries e
            JOIN games j ON j.id = e.game_id
            WHERE e.game_id    = $1
              AND e.no_ranking = true
              AND e.superado   = false
              AND e.pendente   = false
              AND e.arquivado  = false
              AND j.pendente_aprovacao = false
            ORDER BY e.pontuacao DESC, e.criado_em ASC, e.id ASC
            """,
            game_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, nick, nome, pontuacao, foto_url, event_id, criado_em
            FROM entries
            WHERE game_id    = $1
              AND event_id IN (
                  SELECT evento_id FROM placar_eventos
                  WHERE placar_id = $2 AND ativo = true
              )
              AND no_ranking = true
              AND superado   = false
              AND pendente   = false
              AND arquivado  = false
            ORDER BY pontuacao DESC, criado_em ASC, id ASC
            """,
            game_id, placar["id"],
        )
    return [dict(r) for r in rows]


async def listar_lideres(pool: Pool, placar: dict) -> dict:
    """Top 1 de cada game ativo, dentro do escopo do placar."""
    if placar["escopo"] == "global":
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (e.game_id)
                e.game_id, j.slug, e.nick, e.pontuacao
            FROM entries e
            JOIN games j ON j.id = e.game_id
            WHERE e.no_ranking = true
              AND e.superado   = false
              AND e.pendente   = false
              AND e.arquivado  = false
              AND j.ativo      = true
              AND j.pendente_aprovacao = false
            ORDER BY e.game_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC
            """
        )
    else:
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (e.game_id)
                e.game_id, j.slug, e.nick, e.pontuacao
            FROM entries e
            JOIN games j ON j.id = e.game_id
            WHERE e.event_id IN (
                SELECT evento_id FROM placar_eventos
                WHERE placar_id = $1 AND ativo = true
            )
              AND e.no_ranking = true
              AND e.superado   = false
              AND e.pendente   = false
              AND e.arquivado  = false
              AND j.ativo      = true
            ORDER BY e.game_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC
            """,
            placar["id"],
        )
    return {
        str(r["game_id"]): {"slug": r["slug"], "nick": r["nick"], "pontuacao": r["pontuacao"]}
        for r in rows
    }
