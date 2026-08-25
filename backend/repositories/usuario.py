"""
Repository de perfil de usuário — leitura/edição dos campos de `users`
que a pessoa vê/edita na própria tela de perfil.

Ver docs/BACKLOG_2026.md §1 (itens 1.3/1.8) e migration 020. Distinto
de auth/repository.py, que cuida da mecânica de login/sessão — aqui é
só o dado de perfil em si.
"""
from asyncpg import Pool


async def buscar_perfil(pool: Pool, user_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, email, nome, foto_url, status,
               nome_completo, data_nascimento, cidade, estado, telefone,
               avatar_id, criado_em, ultimo_login_em
        FROM users WHERE id = $1
        """,
        user_id,
    )
    return dict(row) if row else None


async def atualizar_perfil(pool: Pool, user_id: str, dados: dict) -> dict | None:
    """Atualiza campos parciais. Chaves não presentes em `dados` ficam
    inalteradas (mesmo padrão de marca_repo.atualizar/evento_repo.atualizar)."""
    row = await pool.fetchrow(
        """
        UPDATE users
        SET nome_completo    = COALESCE($2, nome_completo),
            data_nascimento  = COALESCE($3, data_nascimento),
            cidade           = COALESCE($4, cidade),
            estado           = COALESCE($5, estado),
            telefone         = COALESCE($6, telefone),
            avatar_id        = COALESCE($7, avatar_id)
        WHERE id = $1
        RETURNING id, email, nome, foto_url, status,
                  nome_completo, data_nascimento, cidade, estado, telefone,
                  avatar_id, criado_em, ultimo_login_em
        """,
        user_id,
        dados.get("nome_completo"),
        dados.get("data_nascimento"),
        dados.get("cidade"),
        dados.get("estado"),
        dados.get("telefone"),
        dados.get("avatar_id"),
    )
    return dict(row) if row else None
