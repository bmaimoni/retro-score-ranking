-- ============================================================
-- Retro Score Ranking — migração 015
-- Autenticação e identidade Canal3 (users, identities, nick_claims,
-- sessions, magic_link_tokens) + entradas.user_id
--
-- Especificação completa: docs/AUTH_SPEC.md
--
-- Nota (aprendida nas migrations 011-014): toda tabela nova com RLS
-- precisa de uma policy explícita 'app_user_all' pro app_user — RLS
-- sem policy bloqueia SILENCIOSAMENTE todo SELECT/INSERT/UPDATE (zero
-- linhas, sem erro). Ver SPEC.md §8. Esta migração já nasce com as
-- policies, não deixa pra depois.
-- ============================================================

-- ── 1. Tabela users ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  email            text,
  email_verified   boolean     NOT NULL DEFAULT false,
  nome             text,
  foto_url         text,
  status           text        NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'suspenso')),
  criado_em        timestamptz NOT NULL DEFAULT now(),
  ultimo_login_em  timestamptz
);

COMMENT ON TABLE users IS
  'Identidade canônica de usuário Canal3, compartilhada entre apps '
  '(ranking hoje, quiz/bonificação no futuro). email não é único a '
  'nível de banco — a garantia de não duplicar conta por e-mail vem '
  'da lógica de account linking na aplicação (AUTH_SPEC.md §4.1).';

COMMENT ON COLUMN users.foto_url IS
  'Avatar do perfil (do provedor, ex. Google) — conceito totalmente '
  'separado da foto de evidência de cada score em entradas.foto_url.';

-- ── 2. Tabela identities ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS identities (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider          text        NOT NULL CHECK (provider IN ('google', 'magic_link')),
  provider_user_id  text        NOT NULL,
  email             text        NOT NULL,
  criado_em         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_user_id)
);

COMMENT ON TABLE identities IS
  'Uma linha por provedor vinculado a um usuário. UNIQUE(provider, '
  'provider_user_id) garante que a mesma identidade de provedor nunca '
  'se liga a duas contas diferentes.';

CREATE INDEX IF NOT EXISTS idx_identities_user ON identities(user_id);

-- ── 3. Tabela nick_claims ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nick_claims (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  nick_norm  text        NOT NULL UNIQUE,
  user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  criado_em  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE nick_claims IS
  'Escopo: plataforma inteira, não por app (AUTH_SPEC.md §3). Nick '
  'fica livre até o primeiro login com ele; a partir daí, protegido '
  'para o user_id que reivindicou. UNIQUE(nick_norm) garante que só '
  'uma conta reivindica cada nick.';

CREATE INDEX IF NOT EXISTS idx_nick_claims_user ON nick_claims(user_id);

-- ── 4. Tabela sessions ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  expira_em    timestamptz NOT NULL,
  revogada_em  timestamptz,
  user_agent   text,
  ip_hash      text
);

COMMENT ON TABLE sessions IS
  'id é o próprio valor do cookie de sessão (opaco). TTL de 30 dias, '
  'renovado a cada uso (sliding) — ver AUTH_SPEC.md §5. Revogação é '
  'revogada_em preenchido, não DELETE.';

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_ativa ON sessions(id)
  WHERE revogada_em IS NULL;

-- ── 5. Tabela magic_link_tokens ──────────────────────────────────
CREATE TABLE IF NOT EXISTS magic_link_tokens (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  email       text        NOT NULL,
  token_hash  text        NOT NULL UNIQUE,
  criado_em   timestamptz NOT NULL DEFAULT now(),
  expira_em   timestamptz NOT NULL,
  usado_em    timestamptz
);

COMMENT ON TABLE magic_link_tokens IS
  'token_hash é o hash do token (nunca o token em texto puro, igual '
  'se faz com senha). TTL de 15 min, single-use via usado_em.';

CREATE INDEX IF NOT EXISTS idx_magic_link_tokens_email ON magic_link_tokens(email);

-- ── 6. entradas.user_id ──────────────────────────────────────────
-- Nullable e sem backfill retroativo — entradas antigas continuam
-- com user_id = NULL (envio anônimo, comportamento inalterado).
-- ON DELETE SET NULL: excluir uma conta nunca apaga o histórico de
-- scores, só desvincula a autoria (mesmo princípio de nunca deletar
-- entradas já aplicado ao resto do schema).
ALTER TABLE entradas
  ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_entradas_user ON entradas(user_id)
  WHERE user_id IS NOT NULL;

-- ── 7. RLS nas tabelas novas ──────────────────────────────────────
ALTER TABLE users              ENABLE ROW LEVEL SECURITY;
ALTER TABLE identities         ENABLE ROW LEVEL SECURITY;
ALTER TABLE nick_claims        ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions           ENABLE ROW LEVEL SECURITY;
ALTER TABLE magic_link_tokens  ENABLE ROW LEVEL SECURITY;

-- ── 8. Policies para app_user (mesmo padrão de app_user_all já em
--       uso nas demais tabelas — ver SPEC.md §8) ───────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'users' AND policyname = 'app_user_all') THEN
    CREATE POLICY app_user_all ON users FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'identities' AND policyname = 'app_user_all') THEN
    CREATE POLICY app_user_all ON identities FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'nick_claims' AND policyname = 'app_user_all') THEN
    CREATE POLICY app_user_all ON nick_claims FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'sessions' AND policyname = 'app_user_all') THEN
    CREATE POLICY app_user_all ON sessions FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'magic_link_tokens' AND policyname = 'app_user_all') THEN
    CREATE POLICY app_user_all ON magic_link_tokens FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;

-- ── 9. Permissões para app_user (SELECT/INSERT/UPDATE — sem DELETE,
--       mesmo princípio de mínimo privilégio do resto do projeto;
--       revogação/expiração são sempre UPDATE de coluna, nunca
--       remoção física de linha) ───────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON users              TO app_user;
GRANT SELECT, INSERT, UPDATE ON identities         TO app_user;
GRANT SELECT, INSERT, UPDATE ON nick_claims        TO app_user;
GRANT SELECT, INSERT, UPDATE ON sessions           TO app_user;
GRANT SELECT, INSERT, UPDATE ON magic_link_tokens  TO app_user;
