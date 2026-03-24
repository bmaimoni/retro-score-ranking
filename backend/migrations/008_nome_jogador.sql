-- Retro Score Ranking — migração 008
-- Adiciona campo nome do jogador (nome e sobrenome real)
ALTER TABLE entradas ADD COLUMN IF NOT EXISTS nome text;
