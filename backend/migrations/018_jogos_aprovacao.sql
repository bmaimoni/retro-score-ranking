-- ============================================================
-- Retro Score Ranking — migração 018
-- Fluxo de aprovação de jogos pro catálogo global
--
-- Contexto: com admin escopado (MARCAS_SPEC.md §6), qualquer admin
-- podia criar jogo direto no catálogo GLOBAL, sem checagem de escopo
-- — inconsistente com o modelo (um admin de marca não deveria alterar
-- um catálogo compartilhado por toda a plataforma).
--
-- Novo comportamento: admin não-super cria jogo → nasce
-- pendente_aprovacao=true, já utilizável nos eventos desse admin
-- (auto-vinculado via evento_jogos), mas fora do catálogo/placar
-- geral até um super-admin aprovar. Super-admin também pode mesclar
-- um jogo pendente com um já existente (duplicata).
--
-- Apenas colunas novas em tabela já existente — jogos já tem
-- RLS + policy app_user_all aplicados manualmente (tabela "antiga"),
-- sem mudança necessária aqui.
-- ============================================================

ALTER TABLE jogos
  ADD COLUMN IF NOT EXISTS pendente_aprovacao  boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS criado_por           text,
  ADD COLUMN IF NOT EXISTS mesclado_em_jogo_id  uuid REFERENCES jogos(id) ON DELETE SET NULL;

COMMENT ON COLUMN jogos.pendente_aprovacao IS
  'true = criado por admin não-super, ainda não aprovado pro catálogo '
  '/ placar geral. Já utilizável nos eventos do admin que criou '
  '(vínculo via evento_jogos), só fica de fora da agregação global '
  '(GET /api/jogos sem evento, placar escopo=global) enquanto pendente.';

COMMENT ON COLUMN jogos.criado_por IS
  'Identificador do admin que criou (mesmo padrão de entradas.moderado_por). '
  'NULL para jogos antigos, criados antes desta migração.';

COMMENT ON COLUMN jogos.mesclado_em_jogo_id IS
  'Se este jogo foi identificado como duplicata e mesclado em outro '
  '(entradas e evento_jogos migrados), aponta pra onde. Jogo original '
  'fica com ativo=false, mas nunca é apagado — mantém o rastro.';

CREATE INDEX IF NOT EXISTS idx_jogos_pendente ON jogos(pendente_aprovacao)
  WHERE pendente_aprovacao = true;
