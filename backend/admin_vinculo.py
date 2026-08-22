"""
Repository de admin_vinculos — vincula um usuário a um escopo de
administração (super/marca/evento).

Ver docs/MARCAS_SPEC.md §6 para o desenho completo.
"""
from asyncpg import Pool


async def listar_por_usuario(pool: Pool, user_id: str) -> list[dict]:
    """Vínculos ativos de um usuário — usado pelo middleware de auth
    pra decidir o que ele pode administrar."""
    rows = await pool.fetch(
        """
        SELECT id, user_id, escopo, marca_id, evento_id, ativo, criado_em
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
               av.evento_id, e.nome AS evento_nome,
               av.ativo, av.criado_em
        FROM admin_vinculos av
        JOIN users u ON u.id = av.user_id
        LEFT JOIN marcas  m ON m.id = av.marca_id
        LEFT JOIN eventos e ON e.id = av.evento_id
        ORDER BY av.criado_em DESC
        """
    )
    return [dict(r) for r in rows]


async def criar(
    pool: Pool,
    user_id: str,
    escopo: str,
    marca_id: str | None = None,
    evento_id: str | None = None,
) -> dict:
    """
    Cria um vínculo. Se já existir (mesmo user_id+escopo+alvo, mesmo
    que inativo), reativa em vez de duplicar — mesmo padrão de
    evento_jogos/placar_eventos (idx_admin_vinculos_unico garante isso
    no banco).
    """
    row = await pool.fetchrow(
        """
        INSERT INTO admin_vinculos (user_id, escopo, marca_id, evento_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, escopo, COALESCE(marca_id, '00000000-0000-0000-0000-000000000000'),
                                       COALESCE(evento_id, '00000000-0000-0000-0000-000000000000'))
        DO UPDATE SET ativo = true
        RETURNING id, user_id, escopo, marca_id, evento_id, ativo, criado_em
        """,
        user_id, escopo, marca_id, evento_id,
    )
    return dict(row)


async def atualizar_ativo(pool: Pool, vinculo_id: str, ativo: bool) -> dict | None:
    """Ativa/desativa um vínculo — 'remover' é ativo=false, nunca DELETE
    (app_user não tem essa permissão nesta tabela)."""
    row = await pool.fetchrow(
        """
        UPDATE admin_vinculos SET ativo = $2
        WHERE id = $1
        RETURNING id, user_id, escopo, marca_id, evento_id, ativo, criado_em
        """,
        vinculo_id, ativo,
    )
    return dict(row) if row else None


async def tem_acesso_evento(pool: Pool, user_id: str, evento_id: str) -> bool:
    """
    True se o usuário tem QUALQUER vínculo que autorize agir sobre este
    evento: super, ou marca (cujo marca_id bate com a marca do evento),
    ou evento (direto). Uma única query cobre os 3 casos.
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
             OR (av.escopo = 'marca'  AND av.marca_id  = e.marca_id)
             OR (av.escopo = 'evento' AND av.evento_id = e.id)
          )
        LIMIT 1
        """,
        user_id, evento_id,
    )
    return row is not None


async def listar_eventos_acessiveis(pool: Pool, user_id: str) -> list[str]:
    """
    IDs de todos os eventos que o usuário pode administrar — usado pra
    filtrar feed/pendentes quando o admin não é super (ver
    docs/MARCAS_SPEC.md §6, efeito colateral em feed/pendentes).
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT e.id
        FROM eventos e
        JOIN admin_vinculos av ON (
             av.escopo = 'evento' AND av.evento_id = e.id
          OR av.escopo = 'marca'  AND av.marca_id  = e.marca_id
        )
        WHERE av.user_id = $1 AND av.ativo = true
        """,
        user_id,
    )
    return [str(r["id"]) for r in rows]


async def listar_eventos_acessiveis_detalhado(pool: Pool, user_id: str) -> list[dict]:
    """
    Igual a listar_eventos_acessiveis, mas com nome/slug — usado pelo
    frontend do admin pra montar um seletor de evento (GET /api/admin/me).
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT e.id, e.nome, e.slug
        FROM eventos e
        JOIN admin_vinculos av ON (
             av.escopo = 'evento' AND av.evento_id = e.id
          OR av.escopo = 'marca'  AND av.marca_id  = e.marca_id
        )
        WHERE av.user_id = $1 AND av.ativo = true
        ORDER BY e.nome
        """,
        user_id,
    )
    return [dict(r) for r in rows]
