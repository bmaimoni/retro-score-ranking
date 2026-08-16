-- ============================================================
-- Retro Score Ranking — migração 013
-- Reforça o seed do telão "Hall da Fama Geral" (idempotente)
--
-- Diagnóstico: em produção, GET /api/teloes/geral/config retornou 404
-- mesmo com a migration 011 aplicada sem erro reportado — as tabelas
-- existem (senão o erro seria outro, não um 404 limpo), mas a linha
-- semeada de 'geral' em teloes (e possivelmente placares/telao_jogos)
-- não ficou persistida — provavelmente algo se perdeu ao colar o SQL
-- no editor do Supabase.
--
-- Esta migração é 100% idempotente (ON CONFLICT DO NOTHING em tudo) —
-- segura de rodar tanto para corrigir o ambiente atual quanto numa
-- eventual reaplicação do zero (não duplica nada se já existir).
-- ============================================================

-- 1. Garante o placar global
INSERT INTO placares (nome, slug, escopo)
VALUES ('Hall da Fama Geral', 'geral', 'global')
ON CONFLICT (slug) DO NOTHING;

-- 2. Garante o telão "Hall da Fama Geral" apontando pro placar global
INSERT INTO teloes (nome, slug, placar_id, top_n)
SELECT 'Hall da Fama Geral', 'geral', p.id, 10
FROM placares p
WHERE p.slug = 'geral'
ON CONFLICT (slug) DO NOTHING;

-- 3. Garante os jogos ativos vinculados ao telão, na mesma ordem
--    alfabética que o telao.html sempre usou (ORDER BY nome)
INSERT INTO telao_jogos (telao_id, jogo_id, ordem, ativo)
SELECT
  t.id,
  j.id,
  ROW_NUMBER() OVER (ORDER BY j.nome) - 1,
  true
FROM teloes t
CROSS JOIN jogos j
WHERE t.slug = 'geral'
  AND j.ativo = true
ON CONFLICT (telao_id, jogo_id) DO NOTHING;
