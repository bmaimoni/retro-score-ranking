-- ============================================================
-- Retro Score Ranking — migração 012
-- placar_eventos ganha campo ativo (soft-remove, sem DELETE)
--
-- app_user não tem permissão de DELETE em placar_eventos (mesmo
-- padrão de evento_jogos) — remover um evento de um placar
-- customizado precisa ser um toggle, não um DELETE físico.
-- ============================================================

ALTER TABLE placar_eventos
  ADD COLUMN IF NOT EXISTS ativo boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN placar_eventos.ativo IS
  'false = evento removido do placar customizado, sem apagar a linha '
  '(app_user não tem DELETE nesta tabela — mesmo padrão de evento_jogos).';

-- Índice para a query de ranking por placar customizado
-- (repositories/placar.py filtra por placar_id + ativo=true)
CREATE INDEX IF NOT EXISTS idx_placar_eventos_ativo
  ON placar_eventos(placar_id) WHERE ativo = true;
