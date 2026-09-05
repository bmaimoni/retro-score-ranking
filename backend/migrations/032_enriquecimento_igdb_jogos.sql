-- ============================================================
-- Retro Score Ranking — migração 032
-- Fase 8 do CATALOGO_JOGOS_SPEC.md — enriquecimento de metadado do
-- catálogo a partir da IGDB (resumo, empresas, modos de jogo,
-- franquia, nota externa, classificação etária, screenshot e campos
-- de busca ampliada), pro detalhe expandido do card em
-- admin-jogos.html (PAINEIS_ADMIN_SPEC.md §11).
--
-- O que muda: 9 colunas novas em games, nenhuma tabela nova. Mesmo
-- nível de simplicidade das colunas já existentes (plataforma,
-- generos, geracoes) — string/array livre, sem FK pra tabela de
-- referência, sem índice (dataset de dezenas de jogos hoje).
--
--   games.resumo               — text. Sinopse/descrição (IGDB summary).
--   games.desenvolvedora       — text. Empresa(s) desenvolvedora(s),
--     junção por vírgula se mais de uma (mesmo padrão de `plataforma`).
--   games.publicadora          — text. Idem, papel "publisher".
--   games.modos_jogo           — text[]. Ex: '{Single player,Multiplayer}'.
--   games.modos_multiplayer    — text[]. Achatado das flags booleanas
--     de multiplayer_modes da IGDB (ex: '{Co-op offline,Split-screen}').
--   games.franquias            — text[]. Série/franquia do jogo.
--   games.rating_igdb          — smallint, 0-100. De `total_rating`
--     (média usuários+crítica IGDB) — NUNCA confundir com o ranking
--     real da plataforma (CATALOGO_JOGOS_SPEC.md 8.4), rótulo fixo
--     "Nota IGDB" na UI.
--   games.classificacoes_etarias — text[]. Ex: '{"ESRB: T","PEGI: 12"}'.
--   games.screenshot_url       — text. Uma captura de tela (a primeira
--     retornada pela IGDB) — complementa `capa_url`, que é só a capa.
--   games.palavras_chave       — text[]. Keywords da IGDB — NÃO exibido,
--     só amplia o filtro de texto local (busca por sinônimo/termo).
--   games.nomes_alternativos   — text[]. Títulos alternativos/regionais
--     (ex: nome japonês) — NÃO exibido, mesmo uso de busca ampliada.
--
-- É reversível? Sim — DROP COLUMN desfaz todas, sem FK apontando pra
-- nenhuma delas.
-- Afeta dado existente? Não — nascem NULL em todo game já cadastrado.
-- Populadas depois via resync manual por super (POST
-- /api/admin/games/{id}/resync-igdb, CATALOGO_JOGOS_SPEC.md 8.5) ou no
-- próximo cadastro/atualização vindo da IGDB — sem backfill automático
-- nesta migração.
-- ============================================================

ALTER TABLE games
  ADD COLUMN IF NOT EXISTS resumo                 text,
  ADD COLUMN IF NOT EXISTS desenvolvedora          text,
  ADD COLUMN IF NOT EXISTS publicadora             text,
  ADD COLUMN IF NOT EXISTS modos_jogo              text[],
  ADD COLUMN IF NOT EXISTS modos_multiplayer       text[],
  ADD COLUMN IF NOT EXISTS franquias               text[],
  ADD COLUMN IF NOT EXISTS rating_igdb             smallint,
  ADD COLUMN IF NOT EXISTS classificacoes_etarias  text[],
  ADD COLUMN IF NOT EXISTS screenshot_url          text,
  ADD COLUMN IF NOT EXISTS palavras_chave          text[],
  ADD COLUMN IF NOT EXISTS nomes_alternativos      text[];

COMMENT ON COLUMN games.rating_igdb IS
  'Nota externa da IGDB (total_rating, 0-100), NUNCA o ranking real da
   plataforma — rótulo fixo "Nota IGDB" na UI, nunca ao lado do ranking
   de scores (CATALOGO_JOGOS_SPEC.md 8.4).';

COMMENT ON COLUMN games.palavras_chave IS
  'Keywords da IGDB — não exibido, só amplia o filtro de texto local do
   catálogo (CATALOGO_JOGOS_SPEC.md 8.3).';

COMMENT ON COLUMN games.nomes_alternativos IS
  'Títulos alternativos/regionais da IGDB (ex: nome japonês) — não
   exibido, mesmo uso de busca ampliada (CATALOGO_JOGOS_SPEC.md 8.3).';
