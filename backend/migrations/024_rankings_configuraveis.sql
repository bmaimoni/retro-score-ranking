-- ============================================================
-- Retro Score Ranking — migração 024
-- Fase 4: rankings configuráveis (5 modos de agregação), parcerias
-- entre marcas, metadado de jogo, itens por página configurável
--
-- Especificação completa: docs/RANKINGS_CONFIGURAVEIS_SPEC.md,
-- docs/BACKLOG_2026.md §3 (itens 3.1/3.2/3.3/3.6)
--
-- Puramente aditiva. Nenhum pré-requisito de produção a confirmar.
-- ============================================================

-- ── 1. eventos.modo_ranking ──────────────────────────────────────────
ALTER TABLE eventos ADD COLUMN IF NOT EXISTS modo_ranking text
  NOT NULL DEFAULT 'zerado'
  CHECK (modo_ranking IN ('zerado', 'ultimo_evento', 'marca', 'marca_parceiras', 'geral'));

COMMENT ON COLUMN eventos.modo_ranking IS
  'Como o ranking deste evento é composto (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1):
  zerado = placar próprio, sem herdar nada (comportamento padrão histórico);
  ultimo_evento = referencia o evento anterior mais recente da mesma marca;
  marca = agrega todos os eventos da marca com modo != zerado;
  marca_parceiras = marca + eventos de marcas com parceria ativa (marcas_parcerias);
  geral = placar escopo=global já existente, sem opt-out.
  Todos calculados ao vivo — nenhum dado espelhado, nenhuma linha copiada.';

-- ── 2. marcas.itens_por_pagina ────────────────────────────────────────
ALTER TABLE marcas ADD COLUMN IF NOT EXISTS itens_por_pagina integer
  NOT NULL DEFAULT 20 CHECK (itens_por_pagina > 0);

COMMENT ON COLUMN marcas.itens_por_pagina IS
  'Config única por marca, todo evento dela herda — sem exceção por evento
  (BACKLOG_2026.md §3 item 3.2). Em ranking agregado usa sempre o valor da
  marca "dona" da página sendo visualizada, nunca uma mistura.';

-- ── 3. jogos: metadado opcional ───────────────────────────────────────
ALTER TABLE jogos
  ADD COLUMN IF NOT EXISTS plataforma      text,
  ADD COLUMN IF NOT EXISTS ano_lancamento  integer CHECK (ano_lancamento > 1950),
  ADD COLUMN IF NOT EXISTS capa_url        text,
  ADD COLUMN IF NOT EXISTS gameplay_url    text;

COMMENT ON COLUMN jogos.plataforma IS
  'Texto livre (ex: "Arcade", "Mega Drive") — sem integração externa
  (BACKLOG_2026.md §3 item 3.1); consulta manual, fora do projeto.';
COMMENT ON COLUMN jogos.capa_url IS
  'Mesmo padrão de avatar — super-admin sobe pelo painel via services/storage.py.';

-- ── 4. marcas_parcerias (nova) ────────────────────────────────────────
-- Modelo (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2 decisões #2/#5, §4):
-- cada linha é uma concessão UNIDIRECIONAL "origem libera acesso ao
-- próprio placar pra destino" — origem aparece no modo D (marca +
-- parceiras) de destino. "Liberar" (marca B) cria só a linha B→A,
-- já com efeito imediato (decisão #5) — A já enxerga B em modo D antes
-- mesmo de reciprocar. "Aceitar" (marca A) cria a linha recíproca A→B,
-- fechando a mutualidade descrita na decisão #2. Revogar é ativo=false
-- na PRÓPRIA linha (origem revoga o que ela concedeu) — não afeta a
-- linha da outra marca; a mutualidade pode voltar a ficar assimétrica,
-- e não há problema nisso, "tudo-ou-nada" (decisão #4) é sobre
-- granularidade de evento dentro de uma marca, não sobre simetria
-- entre duas marcas.
CREATE TABLE IF NOT EXISTS marcas_parcerias (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  marca_origem_id  uuid        NOT NULL REFERENCES marcas(id) ON DELETE CASCADE,
  marca_destino_id uuid        NOT NULL REFERENCES marcas(id) ON DELETE CASCADE,
  ativo            boolean     NOT NULL DEFAULT true,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT marcas_parcerias_nao_a_si_mesma CHECK (marca_origem_id != marca_destino_id),
  UNIQUE (marca_origem_id, marca_destino_id)
);

COMMENT ON TABLE marcas_parcerias IS
  'origem libera o próprio placar pra destino ver em modo_ranking=marca_parceiras.
  Direcional — mutualidade é resultado de duas linhas (A→B e B→A), não uma
  propriedade da linha em si. ativo=false em vez de DELETE, mesma convenção
  do projeto inteiro. Toda liberação/aceite/revogação é auditada em
  admin_vinculos_auditoria (decisão #6 — reaproveita a tabela geral já
  desenhada em PERMISSOES_SPEC.md, não é tabela nova).';

CREATE INDEX IF NOT EXISTS idx_marcas_parcerias_destino ON marcas_parcerias(marca_destino_id) WHERE ativo = true;
CREATE INDEX IF NOT EXISTS idx_marcas_parcerias_origem  ON marcas_parcerias(marca_origem_id)  WHERE ativo = true;

ALTER TABLE marcas_parcerias ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'marcas_parcerias' AND policyname = 'app_user_all') THEN
    CREATE POLICY app_user_all ON marcas_parcerias FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE ON marcas_parcerias TO app_user;

-- ── 5. admin_vinculos_auditoria: novo tipo de ação (decisão #6) ───────
-- Reaproveita a tabela — só amplia o CHECK de 'acao' pra incluir os 3
-- eventos de parceria. Parceria é entre MARCAS, não usuários, mas
-- user_alvo_id é NOT NULL — decisão de implementação: grava o
-- próprio ator (quem clicou) em user_alvo_id, e a marca_destino_id
-- (a outra parte da parceria) em detalhes (jsonb). marca_id continua
-- com o mesmo papel de sempre: a marca "sujeito" da ação.
ALTER TABLE admin_vinculos_auditoria DROP CONSTRAINT IF EXISTS admin_vinculos_auditoria_acao_check;
ALTER TABLE admin_vinculos_auditoria ADD CONSTRAINT admin_vinculos_auditoria_acao_check
  CHECK (acao IN (
    'concedido', 'revogado', 'titularidade_transferida',
    'parceria_liberada', 'parceria_aceita', 'parceria_revogada'
  ));
