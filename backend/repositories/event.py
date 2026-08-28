from asyncpg import Pool


async def listar(pool: Pool) -> list[dict]:
    """Todos os events, mais recentes primeiro."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, ativo, publico, logo_url, cor_primaria,
               tipografia, arena_id, modo_ranking, data_inicio, data_fim, criado_em
        FROM events
        ORDER BY criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def listar_abertos(pool: Pool) -> list[dict]:
    """
    Events com visibility='open' — diretório de descoberta da home
    institucional (Fase 8, ARENA_SPEC.md D.1/D.7). Eixo independente
    de 'publico' (acesso via link direto) — aqui exige os dois: só
    faz sentido listar pra descoberta um event que também aceita
    visita direta. Arena 'draft'/'suspended' nunca aparece aqui, nem
    que o event dela seja visibility='open' — mesma trava de B.4 já
    aplicada em arena_repo.listar_com_event_ativo.
    """
    rows = await pool.fetch(
        """
        SELECT e.id, e.nome, e.slug, e.logo_url, m.nome AS arena_nome
        FROM events e
        JOIN arenas m ON m.id = e.arena_id
        WHERE e.ativo = true AND e.publico = true
          AND e.visibility = 'open' AND m.status = 'published'
        ORDER BY e.criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def listar_ativos(pool: Pool) -> list[dict]:
    """Eventos ativos, ordenados por criado_em DESC."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, ativo, publico, logo_url, cor_primaria,
               tipografia, arena_id, modo_ranking, data_inicio, data_fim, criado_em
        FROM events
        WHERE ativo = true
        ORDER BY criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def buscar_por_id(pool: Pool, event_id: str) -> dict | None:
    """Busca event pelo id — usado pra resolver a arena do event
    antes de checar permissão (ver routers/events.py)."""
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug, ativo, publico, logo_url, cor_primaria,
               tipografia, arena_id, modo_ranking, data_inicio, data_fim, criado_em
        FROM events
        WHERE id = $1
        """,
        event_id,
    )
    return dict(row) if row else None


async def buscar_por_slug(pool: Pool, slug: str) -> dict | None:
    """Busca event pelo slug. Retorna None se não existir."""
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug, ativo, publico, logo_url, cor_primaria,
               tipografia, arena_id, modo_ranking, data_inicio, data_fim, criado_em
        FROM events
        WHERE slug = $1
        """,
        slug,
    )
    return dict(row) if row else None


async def buscar_publico_por_slug(pool: Pool, slug: str) -> dict | None:
    """
    Busca event pelo slug para acesso público.
    Retorna None se não existir, inativo ou publico = false.
    """
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug, logo_url, cor_primaria
        FROM events
        WHERE slug    = $1
          AND ativo   = true
          AND publico = true
        """,
        slug,
    )
    return dict(row) if row else None


async def buscar_event_envio_atual_da_arena(pool: Pool, arena_id: str) -> dict | None:
    """
    Resolve o event pra onde apontar o QR/link de envio quando a
    página visualizada está em ranking agregado (BACKLOG_2026.md §3
    item 3.3: 'QR sempre aponta pro event mais recente/ativo da arena
    dona da página'). Prioriza um event cuja janela [data_inicio,
    data_fim] esteja aberta agora; sem nenhum aberto, cai pro mais
    recente por data_inicio — nunca aponta pra um event arquivado ou
    inacessível (mesmo filtro de visibilidade pública de sempre).
    """
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug, ativo, publico, logo_url, cor_primaria,
               tipografia, arena_id, modo_ranking, data_inicio, data_fim, criado_em
        FROM events
        WHERE arena_id = $1 AND ativo = true AND publico = true
        ORDER BY (data_inicio <= now() AND data_fim >= now()) DESC, data_inicio DESC
        LIMIT 1
        """,
        arena_id,
    )
    return dict(row) if row else None


async def criar(pool: Pool, dados: dict) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO events (nome, slug, ativo, publico, logo_url, cor_primaria,
                             tipografia, arena_id, modo_ranking, data_inicio, data_fim)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING id, nome, slug, ativo, publico, logo_url, cor_primaria,
                  tipografia, arena_id, modo_ranking, data_inicio, data_fim, criado_em
        """,
        dados["nome"],
        dados["slug"],
        dados.get("ativo", True),
        dados.get("publico", True),
        dados.get("logo_url"),
        dados.get("cor_primaria"),
        dados.get("tipografia"),
        dados.get("arena_id"),
        dados.get("modo_ranking", "zerado"),
        dados.get("data_inicio"),
        dados.get("data_fim"),
    )
    return dict(row)


async def atualizar(pool: Pool, event_id: str, dados: dict) -> dict | None:
    row = await pool.fetchrow(
        """
        UPDATE events
        SET nome         = COALESCE($2, nome),
            ativo        = COALESCE($3, ativo),
            publico      = COALESCE($4, publico),
            logo_url     = COALESCE($5, logo_url),
            cor_primaria = COALESCE($6, cor_primaria),
            tipografia   = COALESCE($7, tipografia),
            arena_id     = COALESCE($8, arena_id),
            modo_ranking = COALESCE($9, modo_ranking),
            data_inicio  = COALESCE($10, data_inicio),
            data_fim     = COALESCE($11, data_fim)
        WHERE id = $1
        RETURNING id, nome, slug, ativo, publico, logo_url, cor_primaria,
                  tipografia, arena_id, modo_ranking, data_inicio, data_fim, criado_em
        """,
        event_id,
        dados.get("nome"),
        dados.get("ativo"),
        dados.get("publico"),
        dados.get("logo_url"),
        dados.get("cor_primaria"),
        dados.get("tipografia"),
        dados.get("arena_id"),
        dados.get("modo_ranking"),
        dados.get("data_inicio"),
        dados.get("data_fim"),
    )
    return dict(row) if row else None