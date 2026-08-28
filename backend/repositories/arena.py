"""
Repository de arenas — CRUD e resolução de herança de identidade visual.

Ver docs/MARCAS_SPEC.md para o desenho completo. Arena fica acima de
event: cor_primaria, tipografia e logo_url herdam pra event quando o
event não define os seus (event → arena → default da plataforma).
"""
from asyncpg import Pool


async def buscar_por_slug(pool: Pool, slug: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug, cor_primaria, tipografia, logo_url, itens_por_pagina, criado_em
        FROM arenas WHERE slug = $1
        """,
        slug,
    )
    return dict(row) if row else None


async def buscar_por_id(pool: Pool, arena_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug, cor_primaria, tipografia, logo_url, itens_por_pagina, criado_em
        FROM arenas WHERE id = $1
        """,
        arena_id,
    )
    return dict(row) if row else None


async def listar_todas(pool: Pool) -> list[dict]:
    """Todas as arenas — para o painel admin."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, cor_primaria, tipografia, logo_url, itens_por_pagina, criado_em
        FROM arenas ORDER BY criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def criar(
    pool: Pool,
    nome: str,
    slug: str,
    cor_primaria: str | None = None,
    tipografia: str | None = None,
    logo_url: str | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO arenas (nome, slug, cor_primaria, tipografia, logo_url)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, nome, slug, cor_primaria, tipografia, logo_url, criado_em
        """,
        nome, slug, cor_primaria, tipografia, logo_url,
    )
    return dict(row)


async def atualizar(pool: Pool, arena_id: str, dados: dict) -> dict | None:
    """Atualiza campos parciais. Chaves não presentes em `dados` ficam inalteradas."""
    row = await pool.fetchrow(
        """
        UPDATE arenas
        SET nome             = COALESCE($2, nome),
            cor_primaria     = COALESCE($3, cor_primaria),
            tipografia       = COALESCE($4, tipografia),
            logo_url         = COALESCE($5, logo_url),
            itens_por_pagina = COALESCE($6, itens_por_pagina)
        WHERE id = $1
        RETURNING id, nome, slug, cor_primaria, tipografia, logo_url, itens_por_pagina, criado_em
        """,
        arena_id,
        dados.get("nome"),
        dados.get("cor_primaria"),
        dados.get("tipografia"),
        dados.get("logo_url"),
        dados.get("itens_por_pagina"),
    )
    return dict(row) if row else None


async def buscar_owner_user_id(pool: Pool, arena_id: str) -> str | None:
    """
    user_id do titular da arena (arenas.owner_user_id), ou None se a
    arena não tem titular atribuído ainda (nasce NULL — migration 019).
    Usado pela trava de revogação: revogar o vínculo admin do titular
    atual é bloqueado até a titularidade ser transferida (decisão #10
    do docs/PERMISSOES_SPEC.md).
    """
    row = await pool.fetchrow("SELECT owner_user_id FROM arenas WHERE id = $1", arena_id)
    if not row or row["owner_user_id"] is None:
        return None
    return str(row["owner_user_id"])


async def listar_onde_e_dono(pool: Pool, user_id: str) -> list[dict]:
    """
    Arenas onde este user_id é owner_user_id — usado pela trava de
    exclusão de conta (docs/EXCLUSAO_CONTA_SPEC.md decisão #5): pedido
    de exclusão é bloqueado enquanto a pessoa for titular de qualquer
    arena. Lista (não só bool) pra dar mensagem de erro específica.
    """
    rows = await pool.fetch(
        "SELECT id, nome FROM arenas WHERE owner_user_id = $1",
        user_id,
    )
    return [dict(r) for r in rows]


async def transferir_titularidade(pool: Pool, arena_id: str, novo_owner_user_id: str) -> dict | None:
    """
    Atualiza arenas.owner_user_id. Não mexe em memberships — o dono
    antigo mantém o vínculo admin (transferir titularidade ≠ revogar
    acesso, decisão #11 do docs/PERMISSOES_SPEC.md). Quem chama já
    validou que novo_owner_user_id tem vínculo admin ativo na arena.
    """
    row = await pool.fetchrow(
        """
        UPDATE arenas SET owner_user_id = $2
        WHERE id = $1
        RETURNING id, nome, slug, cor_primaria, tipografia, logo_url, owner_user_id, criado_em
        """,
        arena_id, novo_owner_user_id,
    )
    return dict(row) if row else None


async def listar_events_da_arena(pool: Pool, arena_id: str) -> list[dict]:
    """Eventos vinculados a uma arena — para o painel admin."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, ativo, publico, criado_em
        FROM events
        WHERE arena_id = $1
        ORDER BY criado_em DESC
        """,
        arena_id,
    )
    return [dict(r) for r in rows]


async def listar_com_event_ativo(pool: Pool) -> list[dict]:
    """
    Arenas com pelo menos um event ativo+público — critério de "arena
    válida" pro seletor da tela inicial quando não há ?event= na URL
    (docs/BACKLOG_2026.md §2 item 2.1, ponto cego #2: publico=true, não
    precisa estar dentro da janela de envio). Quem chama resolve, por
    arena, qual event oferecer (event_repo.buscar_event_envio_atual_
    da_arena) — não é responsabilidade desta query.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT m.id, m.nome, m.slug, m.logo_url
        FROM arenas m
        JOIN events e ON e.arena_id = m.id
        WHERE e.ativo = true AND e.publico = true
        ORDER BY m.nome
        """
    )
    return [dict(r) for r in rows]


async def resolver_identidade_visual(pool: Pool, event_slug: str) -> dict | None:
    """
    Resolve cor_primaria/tipografia/logo_url de um event aplicando a
    cadeia de herança event → arena → (None, o frontend usa seu
    próprio default) — numa única query com JOIN (ver docs/MARCAS_SPEC.md
    §3: normalizar em tabela separada não compensa nessa escala, a
    resolução já cabe num único round-trip ao banco).

    Retorna None se o event não existir.
    """
    row = await pool.fetchrow(
        """
        SELECT
            e.slug,
            e.nome,
            COALESCE(e.cor_primaria, m.cor_primaria) AS cor_primaria,
            COALESCE(e.tipografia,   m.tipografia)   AS tipografia,
            COALESCE(e.logo_url,     m.logo_url)     AS logo_url
        FROM events e
        LEFT JOIN arenas m ON m.id = e.arena_id
        WHERE e.slug = $1
        """,
        event_slug,
    )
    return dict(row) if row else None
