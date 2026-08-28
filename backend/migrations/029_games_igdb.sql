-- ============================================================
-- Retro Score Ranking — migração 029
-- Fase 9 (wizard pós-ativação) + Fase 1 do CATALOGO_JOGOS_SPEC.md
-- (escolha/cadastro de jogo dentro do wizard) — docs/ARENA_SPEC.md
-- Fase E, docs/CATALOGO_JOGOS_SPEC.md Fase 5
--
-- O que muda: 1 coluna nova em games, nenhuma tabela nova.
--
--   games.igdb_id — bigint, nullable, UNIQUE quando preenchida.
--     Âncora de dedup estrutural pro caminho de busca IGDB
--     (CATALOGO_JOGOS_SPEC.md 5.1): um jogo importado da IGDB nunca
--     duplica no catálogo, mesmo que buscado/selecionado de novo
--     depois — o endpoint de criação reaproveita o jogo existente em
--     vez de tentar criar outro com o mesmo igdb_id. NULL = jogo
--     cadastrado manualmente (sem passar pela IGDB), continua sujeito
--     à fila de aprovação de sempre (migração 018) em vez do
--     dedup estrutural.
--
--   UNIQUE simples (não parcial) — Postgres já trata múltiplos NULL
--   como não-conflitantes numa constraint UNIQUE comum (cada NULL é
--   distinto de outro NULL pra fins de unicidade), então não precisa
--   da forma mais verbosa `UNIQUE ... WHERE igdb_id IS NOT NULL`
--   (constraint parcial) só pra alcançar o mesmo efeito — mais simples
--   já resolve.
--
-- É reversível? Sim — DROP COLUMN desfaz, sem efeito colateral em
-- nenhuma outra tabela (nenhuma FK aponta pra ela).
-- Afeta dado existente? Não — nasce NULL em todo game já cadastrado
-- (nenhum foi importado da IGDB até agora), sem backfill necessário.
-- ============================================================

ALTER TABLE games
  ADD COLUMN IF NOT EXISTS igdb_id bigint UNIQUE;

COMMENT ON COLUMN games.igdb_id IS
  'ID do jogo na IGDB (api.igdb.com) quando cadastrado via busca —
   dedup estrutural (CATALOGO_JOGOS_SPEC.md 5.1). NULL = cadastro
   manual, sujeito à fila de aprovação de sempre (migração 018) em vez
   de aprovação automática.';

CREATE INDEX IF NOT EXISTS idx_games_igdb_id ON games(igdb_id) WHERE igdb_id IS NOT NULL;
