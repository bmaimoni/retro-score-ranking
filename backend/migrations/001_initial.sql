-- ─────────────────────────────────────────────────────────────────────────────
-- Retro Score Ranking — migração inicial
-- Executar no Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ─── TABELA: jogos ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jogos (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    nome       text        NOT NULL,
    slug       text        UNIQUE NOT NULL,
    ativo      boolean     NOT NULL DEFAULT true,
    score_max  integer     CHECK (score_max > 0),   -- NULL = sem limite
    criado_em  timestamptz NOT NULL DEFAULT now()
);

-- ─── TABELA: entradas ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entradas (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    jogo_id      uuid        NOT NULL REFERENCES jogos(id) ON DELETE CASCADE,
    nick         text        NOT NULL,        -- como digitado (exibição)
    nick_norm    text        NOT NULL,        -- lowercase + trim (comparação)
    pontuacao    integer     NOT NULL CHECK (pontuacao > 0),
    foto_url     text        NOT NULL,        -- URL permanente — NUNCA deletar
    no_ranking   boolean     NOT NULL DEFAULT true,    -- false = oculto pelo mod
    superado     boolean     NOT NULL DEFAULT false,   -- score anterior do nick
    pendente     boolean     NOT NULL DEFAULT false,   -- veio pelo rate limit
    ip_hash      text,                                 -- SHA-256(ip + salt)
    criado_em    timestamptz NOT NULL DEFAULT now(),
    moderado_em  timestamptz,
    moderado_por text
);

-- ─── CONSTRAINT: unicidade de nick ativo por jogo ─────────────────────────────
-- Garante no banco que não existem dois registros visíveis do mesmo nick/jogo.
-- Previne race conditions mesmo com requests concorrentes.
ALTER TABLE entradas DROP CONSTRAINT IF EXISTS nick_ativo_unico;
ALTER TABLE entradas ADD CONSTRAINT nick_ativo_unico
    EXCLUDE USING gist (
        nick_norm WITH =,
        jogo_id   WITH =
    ) WHERE (superado = false AND no_ranking = true AND pendente = false);

-- ─── ÍNDICES ──────────────────────────────────────────────────────────────────

-- Ranking público: query mais frequente, filtra estados e ordena por score
CREATE INDEX IF NOT EXISTS idx_ranking
    ON entradas (jogo_id, pontuacao DESC)
    WHERE no_ranking = true AND superado = false AND pendente = false;

-- Rate limit: busca por ip_hash em janela de tempo
CREATE INDEX IF NOT EXISTS idx_ratelimit
    ON entradas (ip_hash, criado_em DESC);

-- Feed do admin: entradas recentes (todas, sem filtro de estado)
CREATE INDEX IF NOT EXISTS idx_admin_feed
    ON entradas (criado_em DESC);

-- Fila de pendentes
CREATE INDEX IF NOT EXISTS idx_pendentes
    ON entradas (criado_em DESC)
    WHERE pendente = true;

-- ─── DADOS INICIAIS (jogos de exemplo) ───────────────────────────────────────
INSERT INTO jogos (nome, slug, score_max) VALUES
    ('Pac-Man',    'pac-man',    999990),
    ('River Raid', 'river-raid', 999900),
    ('Galaga',     'galaga',     999990),
    ('Space Invaders', 'space-invaders', 99990),
    ('Donkey Kong','donkey-kong', 999900)
ON CONFLICT (slug) DO NOTHING;
