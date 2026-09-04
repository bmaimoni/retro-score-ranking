-- ============================================================
-- Retro Score Ranking — migração 031
-- Fase 7 do CATALOGO_JOGOS_SPEC.md — metadado de busca (gênero,
-- geração de plataforma) pro canto "Jogos" (PAINEIS_ADMIN_SPEC.md §10)
--
-- O que muda: 2 colunas novas em games, nenhuma tabela nova.
--
--   games.generos   — text[], nullable. Gêneros do jogo segundo a
--     IGDB (ex: '{Fighting, Action}'). Vários por jogo — um array, não
--     uma FK pra tabela de gêneros (mesmo nível de simplicidade que
--     `plataforma`, que já é string livre).
--
--   games.geracoes  — integer[], nullable. Gerações de console em que
--     o jogo foi lançado (ex: '{3, 4}' pra um jogo que saiu em Arcade
--     E SNES). A geração é um atributo da PLATAFORMA na IGDB, não do
--     jogo — um jogo com várias plataformas carrega o conjunto de
--     gerações delas, não um valor só.
--
-- Nenhuma das duas tem índice — dataset pequeno hoje (12 jogos em
-- produção), mesmo raciocínio já aplicado a `plataforma`/
-- `ano_lancamento` (sem índice). Reavaliar se o catálogo crescer.
--
-- É reversível? Sim — DROP COLUMN desfaz, sem efeito colateral em
-- nenhuma outra tabela (nenhuma FK aponta pra elas).
-- Afeta dado existente? Não — nasce NULL em todo game já cadastrado
-- (nenhum tem esse dado hoje, o campo nunca existiu). Sem backfill.
-- ============================================================

ALTER TABLE games
  ADD COLUMN IF NOT EXISTS generos  text[],
  ADD COLUMN IF NOT EXISTS geracoes integer[];

COMMENT ON COLUMN games.generos IS
  'Gêneros do jogo segundo a IGDB (ex: {Fighting, Action}). Só
   preenchido no caminho de cadastro via IGDB — cadastro manual fica
   NULL (CATALOGO_JOGOS_SPEC.md 7.4).';

COMMENT ON COLUMN games.geracoes IS
  'Gerações de console em que o jogo foi lançado, uma por plataforma
   distinta (ex: {3, 4}). Só preenchido no caminho de cadastro via
   IGDB (CATALOGO_JOGOS_SPEC.md 7.3).';
