-- ─────────────────────────────────────────────────────────────────────────────
-- Retro Score Ranking — migração 007
-- Adiciona coluna arquivado para soft delete de entradas
-- Executar no Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE entradas ADD COLUMN IF NOT EXISTS arquivado boolean NOT NULL DEFAULT false;
ALTER TABLE entradas ADD COLUMN IF NOT EXISTS arquivado_em timestamptz;
ALTER TABLE entradas ADD COLUMN IF NOT EXISTS arquivado_por text;

-- Índice para filtrar arquivados no ranking público
CREATE INDEX IF NOT EXISTS idx_arquivado ON entradas (arquivado) WHERE arquivado = false;

-- Atualiza a constraint do ranking para excluir arquivados
ALTER TABLE entradas DROP CONSTRAINT IF EXISTS nick_ativo_unico;
ALTER TABLE entradas ADD CONSTRAINT nick_ativo_unico
    EXCLUDE USING gist (
        nick_norm WITH =,
        jogo_id   WITH =
    ) WHERE (superado = false AND no_ranking = true AND pendente = false AND arquivado = false);
