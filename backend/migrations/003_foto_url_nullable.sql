-- ─────────────────────────────────────────────────────────────────────────────
-- Retro Score Ranking — migração 003
-- Torna foto_url nullable para suportar uploads sem foto
-- Executar no Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE entradas ALTER COLUMN foto_url DROP NOT NULL;
