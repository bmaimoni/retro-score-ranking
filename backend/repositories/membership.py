"""
Repository de memberships — vincula um usuário a um scope de
administração (super/arena) e, quando scope='marca', a um nível
(admin/moderador) que cascateia pra todos os events daquela arena.

Ver docs/PERMISSOES_SPEC.md para o desenho completo (migration 019 —
substitui o modelo anterior de docs/MARCAS_SPEC.md §6, que incluía
scope='evento').
"""
from asyncpg import Pool


async def listar_por_usuario(pool: Pool, user_id: str) -> list[dict]:
    """Vínculos ativos de um usuário — usado pelo middleware de auth
    pra montar o AdminContext (super + nível por arena)."""
    rows = await pool.fetch(
        """
        SELECT id, user_id, scope, arena_id, role, ativo, criado_em
        FROM memberships
        WHERE user_id = $1 AND ativo = true
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def listar_todos(pool: Pool) -> list[dict]:
    """Todos os vínculos (ativos e inativos), com dados do usuário —
    para o painel de super-admin gerenciar administradores."""
    rows = await pool.fetch(
        """
        SELECT av.id, av.user_id, u.email, u.nome,
               av.scope, av.arena_id, m.nome AS arena_nome,
               av.role, av.ativo, av.criado_em
        FROM memberships av
        JOIN users u ON u.id = av.user_id
        LEFT JOIN arenas  m ON m.id = av.arena_id
        ORDER BY av.criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def criar(
    pool: Pool,
    user_id: str,
    scope: str,
    role: str | None = None,
    arena_id: str | None = None,
) -> dict:
    """
    Cria um vínculo. Se já existir (mesmo user_id+scope+arena, mesmo
    que inativo), reativa em vez de duplicar — e atualiza o nível pro
    valor informado (idx_memberships_unico garante isso no banco).
    """
    row = await pool.fetchrow(
        """
        INSERT INTO memberships (user_id, scope, arena_id, role)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, scope, COALESCE(arena_id, '00000000-0000-0000-0000-000000000000'))
        DO UPDATE SET ativo = true, role = $4
        RETURNING id, user_id, scope, arena_id, role, ativo, criado_em
        """,
        user_id, scope, arena_id, role,
    )
    return dict(row)


async def atualizar_ativo(pool: Pool, vinculo_id: str, ativo: bool) -> dict | None:
    """Ativa/desativa um vínculo — 'remover' é ativo=false, nunca DELETE
    (app_user não tem essa permissão nesta tabela)."""
    row = await pool.fetchrow(
        """
        UPDATE memberships SET ativo = $2
        WHERE id = $1
        RETURNING id, user_id, scope, arena_id, role, ativo, criado_em
        """,
        vinculo_id, ativo,
    )
    return dict(row) if row else None


async def revogar_todos_do_usuario(pool, user_id: str) -> None:
    """Revoga todo membership ativo do usuário — usado na
    anonimização de conta (docs/EXCLUSAO_CONTA_SPEC.md decisão #3).
    `pool` aceita tanto o Pool quanto uma conn dentro de transação."""
    await pool.execute(
        "UPDATE memberships SET ativo = false WHERE user_id = $1 AND ativo = true",
        user_id,
    )


async def buscar_por_id(pool: Pool, vinculo_id: str) -> dict | None:
    """Um vínculo específico — usado pelas checagens de revogação
    (precisa saber arena_id/user_id/role antes de decidir se quem
    está revogando pode)."""
    row = await pool.fetchrow(
        """
        SELECT id, user_id, scope, arena_id, role, ativo, criado_em
        FROM memberships WHERE id = $1
        """,
        vinculo_id,
    )
    return dict(row) if row else None


async def tem_vinculo_admin_ativo(pool: Pool, user_id: str, arena_id: str) -> bool:
    """
    True se o usuário tem vínculo scope='marca', role='admin', ativo,
    exatamente nesta arena. Usado pela transferência de titularidade —
    decisão #11 do docs/PERMISSOES_SPEC.md: só pode virar titular quem
    já é admin vinculado ali, nunca um e-mail arbitrário.
    """
    row = await pool.fetchrow(
        """
        SELECT 1 FROM memberships
        WHERE user_id = $1 AND arena_id = $2
          AND scope = 'marca' AND role = 'admin' AND ativo = true
        LIMIT 1
        """,
        user_id, arena_id,
    )
    return row is not None


async def tem_acesso_event(pool: Pool, user_id: str, event_id: str) -> bool:
    """
    True se o usuário tem QUALQUER vínculo que autorize agir sobre este
    event: super, ou arena (cujo arena_id bate com a arena do event).
    Não distingue nível aqui — moderador também "tem acesso" (modera o
    feed); checagem de nível (admin vs. moderador) é feita à parte, pra
    ações que exigem admin.
    """
    row = await pool.fetchrow(
        """
        SELECT 1
        FROM memberships av
        JOIN events e ON e.id = $2
        WHERE av.user_id = $1
          AND av.ativo   = true
          AND (
                av.scope = 'super'
             OR (av.scope = 'marca' AND av.arena_id = e.arena_id)
          )
        LIMIT 1
        """,
        user_id, event_id,
    )
    return row is not None


async def listar_events_acessiveis(pool: Pool, user_id: str) -> list[str]:
    """
    IDs de todos os events que o usuário pode administrar — usado pra
    filtrar feed/pendentes quando o admin não é super.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT e.id
        FROM events e
        JOIN memberships av
          ON av.scope = 'marca' AND av.arena_id = e.arena_id
        WHERE av.user_id = $1 AND av.ativo = true
        """,
        user_id,
    )
    return [str(r["id"]) for r in rows]


async def listar_events_acessiveis_detalhado(pool: Pool, user_id: str) -> list[dict]:
    """
    Igual a listar_events_acessiveis, mas com nome/slug/role — usado
    pelo frontend do admin pra montar um seletor de event e decidir o
    que esconder (GET /api/admin/me). role vem do vínculo na arena
    daquele event — cada event carrega o nível efetivo da pessoa ali,
    já resolvido, sem o frontend precisar cruzar arena_id à parte.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT e.id, e.nome, e.slug, av.role
        FROM events e
        JOIN memberships av
          ON av.scope = 'marca' AND av.arena_id = e.arena_id
        WHERE av.user_id = $1 AND av.ativo = true
        ORDER BY e.nome
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def listar_por_arenas(pool: Pool, arena_ids: list[str]) -> list[dict]:
    """
    Vínculos scope='marca' (ativos e inativos) restritos às arenas
    informadas, com dados do usuário — mesma forma de listar_todos, mas
    escopado. Usado por GET /api/admin/vinculos pra admin não-super
    (docs/PERMISSOES_SPEC.md §8.2): nunca inclui scope='super', nunca
    arena fora da lista informada.
    """
    if not arena_ids:
        return []
    rows = await pool.fetch(
        """
        SELECT av.id, av.user_id, u.email, u.nome,
               av.scope, av.arena_id, m.nome AS arena_nome,
               av.role, av.ativo, av.criado_em
        FROM memberships av
        JOIN users u ON u.id = av.user_id
        LEFT JOIN arenas  m ON m.id = av.arena_id
        WHERE av.scope = 'marca' AND av.arena_id = ANY($1::uuid[])
        ORDER BY av.criado_em DESC
        """,
        arena_ids,
    )
    return [dict(r) for r in rows]


async def registrar_auditoria(
    pool: Pool,
    acao: str,
    user_alvo_id: str | None,
    realizado_por: str,
    arena_id: str | None = None,
    role: str | None = None,
    detalhes: dict | None = None,
) -> None:
    """
    Grava uma linha em membership_audit_log — toda concessão,
    revogação, transferência de titularidade ou parceria entre arenas
    passa por aqui (decisão #12 do PERMISSOES_SPEC.md, decisão #6 do
    RANKINGS_CONFIGURAVEIS_SPEC.md). Log append-only: sem retorno, sem
    UPDATE/DELETE possível pelo app_user.

    user_alvo_id pode ser None (migration 025) — caso de ação de
    parceria acionada via bootstrap (Bearer <ADMIN_SECRET>, sem
    user_id de sessão real); realizado_por já identifica o ator nesse
    caso ("admin").
    """
    import json

    await pool.execute(
        """
        INSERT INTO membership_audit_log
            (acao, arena_id, user_alvo_id, realizado_por, role, detalhes)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        acao, arena_id, user_alvo_id, realizado_por, role,
        json.dumps(detalhes) if detalhes is not None else None,
    )
