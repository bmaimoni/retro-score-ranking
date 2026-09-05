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
        SELECT id, nome, slug, cor_primaria, tipografia, logo_url, itens_por_pagina,
               status, plan, owner_user_id, criado_em
        FROM arenas ORDER BY criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def listar_nome_slug(pool: Pool) -> list[dict]:
    """Só nome/slug de toda arena — usado pela checagem de colisão
    (B.2/B.4 da Fase 8, ver services/arena_admissao.py). Consulta leve
    de propósito, roda a cada tentativa de criação self-serve."""
    rows = await pool.fetch("SELECT nome, slug FROM arenas")
    return [dict(r) for r in rows]


async def contar_criadas_por_owner_ultimas_24h(pool: Pool, owner_user_id: str) -> int:
    """Rate limit de criação self-serve (B.3/D.6) — sem tabela nova,
    conta direto em arenas. super é isento (G.4), checado no router
    antes de chamar isto."""
    return await pool.fetchval(
        """
        SELECT COUNT(*) FROM arenas
        WHERE owner_user_id = $1 AND criado_em > now() - interval '1 day'
        """,
        owner_user_id,
    )


async def criar(
    pool: Pool,
    nome: str,
    slug: str,
    cor_primaria: str | None = None,
    tipografia: str | None = None,
    logo_url: str | None = None,
    status: str | None = None,
) -> dict:
    """status=None deixa o DEFAULT da coluna ('published') decidir —
    usado pelo caminho super, que nunca passa por admissão (B.4). O
    caminho self-serve (routers/arenas_admin.py) sempre passa um
    status explícito ('published' ou 'draft', conforme a heurística)."""
    row = await pool.fetchrow(
        """
        INSERT INTO arenas (nome, slug, cor_primaria, tipografia, logo_url, status)
        VALUES ($1, $2, $3, $4, $5, COALESCE($6, 'published'))
        RETURNING id, nome, slug, cor_primaria, tipografia, logo_url, status, plan, criado_em
        """,
        nome, slug, cor_primaria, tipografia, logo_url, status,
    )
    return dict(row)


async def listar_pendentes(pool: Pool) -> list[dict]:
    """Fila de revisão do super (B.4) — arenas status='draft'."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, logo_url, owner_user_id, criado_em
        FROM arenas WHERE status = 'draft'
        ORDER BY criado_em ASC
        """
    )
    return [dict(r) for r in rows]


async def listar_suspensas(pool: Pool) -> list[dict]:
    """Arenas suspensas (docs/PAINEIS_ADMIN_SPEC.md II.2/III.2) — sem
    isso, suspender pela UI era ação só de ida: nenhum jeito de ver
    quem está suspenso pra poder reativar depois."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, logo_url, owner_user_id, criado_em
        FROM arenas WHERE status = 'suspended'
        ORDER BY criado_em ASC
        """
    )
    return [dict(r) for r in rows]


async def atualizar_status(pool: Pool, arena_id: str, status: str) -> dict | None:
    """Aprovar ('published'), rejeitar/suspender ('suspended') uma
    arena — sempre ação de super."""
    row = await pool.fetchrow(
        """
        UPDATE arenas SET status = $2 WHERE id = $1
        RETURNING id, nome, slug, status, owner_user_id, criado_em
        """,
        arena_id, status,
    )
    return dict(row) if row else None


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


async def listar_resumo_events_da_arena(pool: Pool, arena_id: str) -> list[dict]:
    """Events da arena com janela de envio e contagem de recordes —
    base da tela inicial do painel (docs/PAINEIS_ADMIN_SPEC.md F0.3).
    'Recordes' = entries não-arquivadas (F0.7) — inclui pendente/oculta
    (ainda é um envio real), exclui só o formalmente invalidado."""
    rows = await pool.fetch(
        """
        SELECT ev.id, ev.nome, ev.slug, ev.ativo, ev.publico,
               ev.data_inicio, ev.data_fim, ev.criado_em,
               COUNT(e.id) FILTER (WHERE NOT e.arquivado) AS total_recordes
        FROM events ev
        LEFT JOIN entries e ON e.event_id = ev.id
        WHERE ev.arena_id = $1
        GROUP BY ev.id
        ORDER BY ev.criado_em DESC
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

    status = 'published' obrigatório (Fase 8, ARENA_SPEC.md B.4) —
    arena 'draft' (sinalizada por heurística de risco, aguardando
    revisão de super) nunca aparece em superfície pública nenhuma,
    mesmo que já tenha event ativo+público configurado.

    visibility = 'open' também obrigatório (D.7) — antes da Fase 8
    esta query não tinha esse filtro (não existia o conceito ainda);
    sem ele, qualquer Arena self-serve nova vazaria em descoberta
    pública mesmo com o event nascendo 'private' por padrão. Migração
    028 já dá 'open' explícito pros events das Arenas legadas, então
    este filtro não muda o comportamento observável de hoje — só
    fecha o vazamento pra toda Arena self-serve daqui pra frente.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT m.id, m.nome, m.slug, m.logo_url
        FROM arenas m
        JOIN events e ON e.arena_id = m.id
        WHERE e.ativo = true AND e.publico = true
          AND m.status = 'published' AND e.visibility = 'open'
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


# ── Deleção física real (SUPER_SPEC.md §7, Fase 4) ──────────────

async def contar_events(pool: Pool, arena_id: str) -> int:
    """Qualquer event, ativo ou arquivado — usado pra decidir se a
    arena pode ser apagada de vez (só quando zero)."""
    return await pool.fetchval("SELECT COUNT(*) FROM events WHERE arena_id = $1", arena_id)


async def deletar_se_sem_events(pool: Pool, arena_id: str) -> bool:
    """Apaga a arena só se ela não tiver nenhum event — checagem e
    exclusão na mesma query (atômico), sem race entre contar e apagar.
    events.arena_id é NOT NULL (migration 019): sem essa guarda, apagar
    uma arena com event bateria erro de constraint no banco (a FK é
    SET NULL, mas a coluna não aceita NULL), não um estado limpo."""
    row = await pool.fetchrow(
        """
        DELETE FROM arenas
        WHERE id = $1 AND NOT EXISTS (SELECT 1 FROM events WHERE arena_id = $1)
        RETURNING id
        """,
        arena_id,
    )
    return row is not None


async def listar_vazias(pool: Pool) -> list[dict]:
    """Arenas sem nenhum event — únicas candidatas seguras a apagar de
    vez (console.html só oferece o botão pra essas)."""
    rows = await pool.fetch(
        """
        SELECT a.id, a.nome, a.slug, a.criado_em
        FROM arenas a
        WHERE NOT EXISTS (SELECT 1 FROM events e WHERE e.arena_id = a.id)
        ORDER BY a.criado_em DESC
        """
    )
    return [dict(r) for r in rows]
