"""
Repository de admin_vinculos — vincula um usuário a um escopo de
administração (super/marca) e, quando escopo='marca', a um nível
(admin/moderador) que cascateia pra todos os eventos daquela marca.

Ver docs/PERMISSOES_SPEC.md para o desenho completo (migration 019 —
substitui o modelo anterior de docs/MARCAS_SPEC.md §6, que incluía
escopo='evento').
"""
from asyncpg import Pool


async def listar_por_usuario(pool: Pool, user_id: str) -> list[dict]:
    """Vínculos ativos de um usuário — usado pelo middleware de auth
    pra montar o AdminContext (super + nível por marca)."""
    rows = await pool.fetch(
        """
        SELECT id, user_id, escopo, marca_id, nivel, ativo, criado_em
        FROM admin_vinculos
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
               av.escopo, av.marca_id, m.nome AS marca_nome,
               av.nivel, av.ativo, av.criado_em
        FROM admin_vinculos av
        JOIN users u ON u.id = av.user_id
        LEFT JOIN marcas  m ON m.id = av.marca_id
        ORDER BY av.criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def criar(
    pool: Pool,
    user_id: str,
    escopo: str,
    nivel: str | None = None,
    marca_id: str | None = None,
) -> dict:
    """
    Cria um vínculo. Se já existir (mesmo user_id+escopo+marca, mesmo
    que inativo), reativa em vez de duplicar — e atualiza o nível pro
    valor informado (idx_admin_vinculos_unico garante isso no banco).
    """
    row = await pool.fetchrow(
        """
        INSERT INTO admin_vinculos (user_id, escopo, marca_id, nivel)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, escopo, COALESCE(marca_id, '00000000-0000-0000-0000-000000000000'))
        DO UPDATE SET ativo = true, nivel = $4
        RETURNING id, user_id, escopo, marca_id, nivel, ativo, criado_em
        """,
        user_id, escopo, marca_id, nivel,
    )
    return dict(row)


async def atualizar_ativo(pool: Pool, vinculo_id: str, ativo: bool) -> dict | None:
    """Ativa/desativa um vínculo — 'remover' é ativo=false, nunca DELETE
    (app_user não tem essa permissão nesta tabela)."""
    row = await pool.fetchrow(
        """
        UPDATE admin_vinculos SET ativo = $2
        WHERE id = $1
        RETURNING id, user_id, escopo, marca_id, nivel, ativo, criado_em
        """,
        vinculo_id, ativo,
    )
    return dict(row) if row else None


async def revogar_todos_do_usuario(pool, user_id: str) -> None:
    """Revoga todo admin_vinculo ativo do usuário — usado na
    anonimização de conta (docs/EXCLUSAO_CONTA_SPEC.md decisão #3).
    `pool` aceita tanto o Pool quanto uma conn dentro de transação."""
    await pool.execute(
        "UPDATE admin_vinculos SET ativo = false WHERE user_id = $1 AND ativo = true",
        user_id,
    )


async def buscar_por_id(pool: Pool, vinculo_id: str) -> dict | None:
    """Um vínculo específico — usado pelas checagens de revogação
    (precisa saber marca_id/user_id/nivel antes de decidir se quem
    está revogando pode)."""
    row = await pool.fetchrow(
        """
        SELECT id, user_id, escopo, marca_id, nivel, ativo, criado_em
        FROM admin_vinculos WHERE id = $1
        """,
        vinculo_id,
    )
    return dict(row) if row else None


async def tem_vinculo_admin_ativo(pool: Pool, user_id: str, marca_id: str) -> bool:
    """
    True se o usuário tem vínculo escopo='marca', nivel='admin', ativo,
    exatamente nesta marca. Usado pela transferência de titularidade —
    decisão #11 do docs/PERMISSOES_SPEC.md: só pode virar titular quem
    já é admin vinculado ali, nunca um e-mail arbitrário.
    """
    row = await pool.fetchrow(
        """
        SELECT 1 FROM admin_vinculos
        WHERE user_id = $1 AND marca_id = $2
          AND escopo = 'marca' AND nivel = 'admin' AND ativo = true
        LIMIT 1
        """,
        user_id, marca_id,
    )
    return row is not None


async def tem_acesso_evento(pool: Pool, user_id: str, evento_id: str) -> bool:
    """
    True se o usuário tem QUALQUER vínculo que autorize agir sobre este
    evento: super, ou marca (cujo marca_id bate com a marca do evento).
    Não distingue nível aqui — moderador também "tem acesso" (modera o
    feed); checagem de nível (admin vs. moderador) é feita à parte, pra
    ações que exigem admin.
    """
    row = await pool.fetchrow(
        """
        SELECT 1
        FROM admin_vinculos av
        JOIN eventos e ON e.id = $2
        WHERE av.user_id = $1
          AND av.ativo   = true
          AND (
                av.escopo = 'super'
             OR (av.escopo = 'marca' AND av.marca_id = e.marca_id)
          )
        LIMIT 1
        """,
        user_id, evento_id,
    )
    return row is not None


async def listar_eventos_acessiveis(pool: Pool, user_id: str) -> list[str]:
    """
    IDs de todos os eventos que o usuário pode administrar — usado pra
    filtrar feed/pendentes quando o admin não é super.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT e.id
        FROM eventos e
        JOIN admin_vinculos av
          ON av.escopo = 'marca' AND av.marca_id = e.marca_id
        WHERE av.user_id = $1 AND av.ativo = true
        """,
        user_id,
    )
    return [str(r["id"]) for r in rows]


async def listar_eventos_acessiveis_detalhado(pool: Pool, user_id: str) -> list[dict]:
    """
    Igual a listar_eventos_acessiveis, mas com nome/slug/nivel — usado
    pelo frontend do admin pra montar um seletor de evento e decidir o
    que esconder (GET /api/admin/me). nivel vem do vínculo na marca
    daquele evento — cada evento carrega o nível efetivo da pessoa ali,
    já resolvido, sem o frontend precisar cruzar marca_id à parte.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT e.id, e.nome, e.slug, av.nivel
        FROM eventos e
        JOIN admin_vinculos av
          ON av.escopo = 'marca' AND av.marca_id = e.marca_id
        WHERE av.user_id = $1 AND av.ativo = true
        ORDER BY e.nome
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def registrar_auditoria(
    pool: Pool,
    acao: str,
    user_alvo_id: str | None,
    realizado_por: str,
    marca_id: str | None = None,
    nivel: str | None = None,
    detalhes: dict | None = None,
) -> None:
    """
    Grava uma linha em admin_vinculos_auditoria — toda concessão,
    revogação, transferência de titularidade ou parceria entre marcas
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
        INSERT INTO admin_vinculos_auditoria
            (acao, marca_id, user_alvo_id, realizado_por, nivel, detalhes)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        acao, marca_id, user_alvo_id, realizado_por, nivel,
        json.dumps(detalhes) if detalhes is not None else None,
    )
