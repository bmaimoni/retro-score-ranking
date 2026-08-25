-- ============================================================
-- Retro Score Ranking — migração 020
-- Fase 2: perfil de usuário, modelo de troca de nickname,
-- exclusão de conta (janela de cancelamento + trava de titularidade)
--
-- Especificação completa: docs/NICKNAME_SPEC.md, docs/EXCLUSAO_CONTA_SPEC.md,
-- docs/BACKLOG_2026.md §1
--
-- Puramente aditiva — não remove nem reescreve dado existente. Nenhum
-- pré-requisito de produção a confirmar antes de rodar (diferente da
-- migration 019, que dependia de zero eventos órfãos).
--
-- Nota (aprendida nas migrations 011-014, repetida em toda migração
-- desde então): toda tabela nova com RLS precisa de policy explícita
-- 'app_user_all' pro app_user — RLS sem policy bloqueia SILENCIOSAMENTE
-- todo SELECT/INSERT/UPDATE (zero linhas, sem erro).
-- ============================================================

-- ── 1. avatares (nova tabela — galeria curada por super) ────────────
CREATE TABLE IF NOT EXISTS avatares (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  nome       text        NOT NULL,
  url        text        NOT NULL,
  ativo      boolean     NOT NULL DEFAULT true,
  criado_em  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE avatares IS
  'Galeria de avatares curada — só super-admin cadastra/desativa '
  '(BACKLOG_2026.md §1, ponto cego #3). Upload livre pelo usuário fica '
  'fora de escopo por ora (precisaria de moderação de imagem que não '
  'existe). Concorre com users.foto_url (do provedor OAuth) pela '
  '"imagem de perfil resolvida" — avatar vence quando escolhido.';

ALTER TABLE avatares ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'avatares' AND policyname = 'app_user_all') THEN
    CREATE POLICY app_user_all ON avatares FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE ON avatares TO app_user;

-- ── 2. users: campos novos de perfil + status='excluido' ─────────────
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS nome_completo           text,
  ADD COLUMN IF NOT EXISTS data_nascimento         date,
  ADD COLUMN IF NOT EXISTS cidade                  text,
  ADD COLUMN IF NOT EXISTS estado                  text,
  ADD COLUMN IF NOT EXISTS telefone                text,
  ADD COLUMN IF NOT EXISTS avatar_id               uuid REFERENCES avatares(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS exclusao_solicitada_em  timestamptz;

COMMENT ON COLUMN users.avatar_id IS
  'Avatar da galeria curada escolhido pelo usuário — vence users.foto_url '
  '(do provedor OAuth) quando definido. NULL = usa foto_url ou default.';

COMMENT ON COLUMN users.exclusao_solicitada_em IS
  'Quando a exclusão de conta foi solicitada — controla a janela de 30 '
  'dias de cancelamento (EXCLUSAO_CONTA_SPEC.md decisão #2). NULL = sem '
  'solicitação em andamento. Voltar a NULL = pessoa desistiu dentro da '
  'janela. Anonimização de verdade acontece só depois dos 30 dias, '
  'disparada por ação humana (sem job agendado — mesmo princípio de '
  'NICKNAME_SPEC.md §4).';

-- status ganha 'excluido' — distinto de 'suspenso' (moderação) por
-- decisão #1 do EXCLUSAO_CONTA_SPEC.md, mesmo com mecânica parecida.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_check;
ALTER TABLE users ADD CONSTRAINT users_status_check
  CHECK (status IN ('ativo', 'suspenso', 'excluido'));

-- ── 3. nick_claims: soft-release (decisão #5 do NICKNAME_SPEC.md) ────
ALTER TABLE nick_claims ADD COLUMN IF NOT EXISTS ativo boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN nick_claims.ativo IS
  'false = nick liberado (pessoa trocou) — a reivindicação em si nunca '
  'é apagada, só marcada inativa (mesmo padrão de evento_jogos/'
  'admin_vinculos/telao_jogos). Índice único de nick_norm é parcial '
  '(WHERE ativo=true) — permite múltiplas linhas históricas do mesmo '
  'nick, uma por dono ao longo do tempo, só uma ativa por vez.';

-- Troca o UNIQUE(nick_norm) simples (bloquearia reivindicar um nick já
-- liberado) por um índice único parcial.
ALTER TABLE nick_claims DROP CONSTRAINT IF EXISTS nick_claims_nick_norm_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_nick_claims_nick_norm_ativo
  ON nick_claims (nick_norm) WHERE ativo = true;

-- ── 4. nick_troca_forcada_auditoria (nova tabela) ─────────────────────
-- Não reaproveita admin_vinculos_auditoria — domínio diferente (troca
-- de nick não é concessão/revogação de vínculo administrativo);
-- marca_id e nivel não fariam sentido nessa ação.
CREATE TABLE IF NOT EXISTS nick_troca_forcada_auditoria (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  nick_anterior  text        NOT NULL,
  nick_novo      text        NOT NULL,
  realizado_por  text        NOT NULL,
  criado_em      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE nick_troca_forcada_auditoria IS
  'Log de toda troca de nick forçada por admin/moderador, sem respeitar '
  'o cooldown de 30 dias (decisão #9 do NICKNAME_SPEC.md) — uso previsto: '
  'nick ofensivo/impróprio, especialmente relevante por exibição pública '
  'em telão. Nunca editável nem apagável pelo app_user (só INSERT) — é '
  'log, não estado.';

ALTER TABLE nick_troca_forcada_auditoria ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'nick_troca_forcada_auditoria' AND policyname = 'app_user_all'
  ) THEN
    CREATE POLICY app_user_all ON nick_troca_forcada_auditoria
      FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;

GRANT SELECT, INSERT ON nick_troca_forcada_auditoria TO app_user;

-- ── 5. entradas.pendente_motivo (distingue rate_limit de identificação
--       ambígua, decisão #7 do NICKNAME_SPEC.md — mesmo campo pendente,
--       sem tabela nova) ────────────────────────────────────────────
ALTER TABLE entradas ADD COLUMN IF NOT EXISTS pendente_motivo text
  CHECK (pendente_motivo IN ('rate_limit', 'identificacao_ambigua'));

COMMENT ON COLUMN entradas.pendente_motivo IS
  'Por que esta entrada está pendente — rate_limit (fluxo original, '
  'SPEC.md §5.2) ou identificacao_ambigua (nick liberado reivindicado '
  'de novo, entrada antiga sem user_id nem nome — NICKNAME_SPEC.md '
  'decisão #7). NULL só em entradas antigas de antes desta coluna '
  'existir com pendente=false.';

-- Backfill: toda entrada pendente hoje é rate_limit — único motivo que
-- existia antes desta migração.
UPDATE entradas SET pendente_motivo = 'rate_limit'
  WHERE pendente = true AND pendente_motivo IS NULL;
