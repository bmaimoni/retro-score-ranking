-- ============================================================
-- Retro Score Ranking — migração 023
-- Fase 3: seguir jogadores, feed de atividade por superação de score
--
-- Especificação completa: docs/SEGUIR_SPEC.md
--
-- Puramente aditiva. Nenhum pré-requisito de produção a confirmar.
-- ============================================================

CREATE TABLE IF NOT EXISTS seguidores (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  seguidor_id  uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  seguido_id   uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ativo        boolean     NOT NULL DEFAULT true,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT seguidores_nao_a_si_mesmo CHECK (seguidor_id != seguido_id),
  UNIQUE (seguidor_id, seguido_id)
);

COMMENT ON TABLE seguidores IS
  'Vínculo de "seguir" entre user_ids — plataforma inteira, sem escopo '
  'de marca/evento (docs/SEGUIR_SPEC.md decisão #8). ativo=false em vez '
  'de DELETE (deixar de seguir), mesmo padrão de evento_jogos/'
  'admin_vinculos/nick_claims — não estava no §4 original da spec, mas '
  'segue a convenção estabelecida no projeto inteiro (CLAUDE.md): nunca '
  'DELETE físico em dado que já existe no produto. UNIQUE(seguidor_id, '
  'seguido_id) não é parcial (diferente de nick_claims) — aqui o par '
  'em si é a identidade estável; re-seguir reativa a MESMA linha, não '
  'cria uma nova.';

CREATE INDEX IF NOT EXISTS idx_seguidores_seguidor ON seguidores(seguidor_id) WHERE ativo = true;
CREATE INDEX IF NOT EXISTS idx_seguidores_seguido   ON seguidores(seguido_id)  WHERE ativo = true;

ALTER TABLE seguidores ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'seguidores' AND policyname = 'app_user_all') THEN
    CREATE POLICY app_user_all ON seguidores FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE ON seguidores TO app_user;
