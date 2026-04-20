-- ============================================================
-- Retro Score Ranking — migração 010
-- Multi-evento: evento_jogos, campos em eventos,
--               associação de scores órfãos ao canal3expo
-- ============================================================

-- ── 1. Novos campos em eventos ────────────────────────────────
ALTER TABLE eventos
  ADD COLUMN IF NOT EXISTS logo_url      text,
  ADD COLUMN IF NOT EXISTS cor_primaria  text,
  ADD COLUMN IF NOT EXISTS publico       boolean NOT NULL DEFAULT true;

-- publico = false → telão e ranking ficam inacessíveis publicamente
COMMENT ON COLUMN eventos.publico IS
  'false = telão e ranking inacessíveis publicamente (admin pode travar)';

-- ── 2. Tabela evento_jogos (N:N eventos × jogos) ─────────────
CREATE TABLE IF NOT EXISTS evento_jogos (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  evento_id  uuid        NOT NULL REFERENCES eventos(id)  ON DELETE CASCADE,
  jogo_id    uuid        NOT NULL REFERENCES jogos(id)    ON DELETE RESTRICT,
  ativo      boolean     NOT NULL DEFAULT true,
  ordem      int         NOT NULL DEFAULT 0,
  criado_em  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (evento_id, jogo_id)
);

COMMENT ON TABLE evento_jogos IS
  'Vincula jogos a eventos. Jogo com scores não pode ser removido (RESTRICT).';

CREATE INDEX IF NOT EXISTS idx_evento_jogos_evento
  ON evento_jogos(evento_id) WHERE ativo = true;

-- ── 3. Garante que o evento canal3expo existe ─────────────────
INSERT INTO eventos (nome, slug, ativo, publico)
VALUES ('Canal3 Expo', 'canal3expo', true, true)
ON CONFLICT (slug) DO NOTHING;

-- ── 4. Vincula todos os jogos existentes ao canal3expo ────────
INSERT INTO evento_jogos (evento_id, jogo_id, ativo, ordem)
SELECT
  (SELECT id FROM eventos WHERE slug = 'canal3expo'),
  j.id,
  true,
  ROW_NUMBER() OVER (ORDER BY j.nome) - 1
FROM jogos j
ON CONFLICT (evento_id, jogo_id) DO NOTHING;

-- ── 5. Associa scores órfãos (evento_id IS NULL) ao canal3expo ─
UPDATE entradas
SET evento_id = (SELECT id FROM eventos WHERE slug = 'canal3expo')
WHERE evento_id IS NULL;

-- ── 6. Índice para queries por evento+jogo (ranking filtrado) ──
CREATE INDEX IF NOT EXISTS idx_entradas_evento_jogo
  ON entradas(evento_id, jogo_id)
  WHERE no_ranking = true
    AND superado   = false
    AND pendente   = false
    AND arquivado  = false;

-- ── 7. RLS na nova tabela ─────────────────────────────────────
ALTER TABLE evento_jogos ENABLE ROW LEVEL SECURITY;

-- ── 8. Permissões para app_user ───────────────────────────────
GRANT SELECT, INSERT, UPDATE ON evento_jogos TO app_user;
