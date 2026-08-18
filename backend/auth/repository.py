"""
Repository de autenticação — SQL cru para as tabelas de auth
(users, identities, nick_claims, sessions, magic_link_tokens).

Ver docs/AUTH_SPEC.md §3 para o desenho completo, e migration 015
para o schema.
"""
from asyncpg import Pool


# ── users ──────────────────────────────────────────────────────

async def buscar_usuario_por_id(pool: Pool, user_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, email, email_verified, nome, foto_url, status,
               criado_em, ultimo_login_em
        FROM users WHERE id = $1
        """,
        user_id,
    )
    return dict(row) if row else None


async def buscar_usuario_por_email(pool: Pool, email: str) -> dict | None:
    """
    Busca por e-mail para account linking (AUTH_SPEC.md §4.1) — só deve
    ser usado quando o e-mail do provedor vem verificado.
    """
    row = await pool.fetchrow(
        """
        SELECT id, email, email_verified, nome, foto_url, status,
               criado_em, ultimo_login_em
        FROM users WHERE email = $1
        ORDER BY criado_em ASC
        LIMIT 1
        """,
        email,
    )
    return dict(row) if row else None


async def criar_usuario(
    pool: Pool,
    email: str | None,
    email_verified: bool,
    nome: str | None = None,
    foto_url: str | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO users (email, email_verified, nome, foto_url, ultimo_login_em)
        VALUES ($1, $2, $3, $4, now())
        RETURNING id, email, email_verified, nome, foto_url, status,
                  criado_em, ultimo_login_em
        """,
        email, email_verified, nome, foto_url,
    )
    return dict(row)


async def atualizar_ultimo_login(pool: Pool, user_id: str) -> None:
    await pool.execute(
        "UPDATE users SET ultimo_login_em = now() WHERE id = $1", user_id
    )


# ── identities ─────────────────────────────────────────────────

async def buscar_identity(pool: Pool, provider: str, provider_user_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, user_id, provider, provider_user_id, email, criado_em
        FROM identities
        WHERE provider = $1 AND provider_user_id = $2
        """,
        provider, provider_user_id,
    )
    return dict(row) if row else None


async def criar_identity(
    pool: Pool,
    user_id: str,
    provider: str,
    provider_user_id: str,
    email: str,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO identities (user_id, provider, provider_user_id, email)
        VALUES ($1, $2, $3, $4)
        RETURNING id, user_id, provider, provider_user_id, email, criado_em
        """,
        user_id, provider, provider_user_id, email,
    )
    return dict(row)


# ── nick_claims ────────────────────────────────────────────────

async def buscar_nick_claim(pool: Pool, nick_norm: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT id, nick_norm, user_id, criado_em FROM nick_claims WHERE nick_norm = $1",
        nick_norm,
    )
    return dict(row) if row else None


async def criar_nick_claim(pool: Pool, nick_norm: str, user_id: str) -> dict:
    """
    Reivindica um nick. Levanta erro de unique constraint se outro
    user_id já tiver reivindicado — o service decide o que fazer com
    isso (ver services/nick_claim.py).
    """
    row = await pool.fetchrow(
        """
        INSERT INTO nick_claims (nick_norm, user_id)
        VALUES ($1, $2)
        RETURNING id, nick_norm, user_id, criado_em
        """,
        nick_norm, user_id,
    )
    return dict(row)


# ── sessions ───────────────────────────────────────────────────

async def criar_sessao(
    pool: Pool,
    user_id: str,
    ttl_days: int,
    user_agent: str | None = None,
    ip_hash: str | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO sessions (user_id, expira_em, user_agent, ip_hash)
        VALUES ($1, now() + make_interval(days => $2), $3, $4)
        RETURNING id, user_id, criado_em, expira_em, revogada_em
        """,
        user_id, ttl_days, user_agent, ip_hash,
    )
    return dict(row)


async def buscar_sessao_ativa(pool: Pool, session_id: str) -> dict | None:
    """Só retorna a sessão se não revogada e ainda dentro do TTL."""
    row = await pool.fetchrow(
        """
        SELECT id, user_id, criado_em, expira_em, revogada_em
        FROM sessions
        WHERE id = $1
          AND revogada_em IS NULL
          AND expira_em > now()
        """,
        session_id,
    )
    return dict(row) if row else None


async def renovar_sessao(pool: Pool, session_id: str, ttl_days: int) -> None:
    """Sliding renewal — cada uso empurra o TTL pra frente (AUTH_SPEC.md §5)."""
    await pool.execute(
        "UPDATE sessions SET expira_em = now() + make_interval(days => $2) WHERE id = $1",
        session_id, ttl_days,
    )


async def revogar_sessao(pool: Pool, session_id: str) -> None:
    """Logout — nunca DELETE, sempre revogada_em (ver migration 015)."""
    await pool.execute(
        "UPDATE sessions SET revogada_em = now() WHERE id = $1 AND revogada_em IS NULL",
        session_id,
    )


# ── magic_link_tokens ──────────────────────────────────────────

async def criar_magic_link_token(
    pool: Pool, email: str, token_hash: str, ttl_minutes: int
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO magic_link_tokens (email, token_hash, expira_em)
        VALUES ($1, $2, now() + make_interval(mins => $3))
        RETURNING id, email, criado_em, expira_em
        """,
        email, token_hash, ttl_minutes,
    )
    return dict(row)


async def buscar_magic_link_token_valido(pool: Pool, token_hash: str) -> dict | None:
    """Só retorna se não expirado e ainda não usado (single-use)."""
    row = await pool.fetchrow(
        """
        SELECT id, email, token_hash, criado_em, expira_em, usado_em
        FROM magic_link_tokens
        WHERE token_hash = $1
          AND expira_em > now()
          AND usado_em IS NULL
        """,
        token_hash,
    )
    return dict(row) if row else None


async def marcar_magic_link_usado(pool: Pool, token_id: str) -> None:
    await pool.execute(
        "UPDATE magic_link_tokens SET usado_em = now() WHERE id = $1", token_id
    )
