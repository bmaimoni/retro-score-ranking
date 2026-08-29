-- ============================================================
-- Retro Score Ranking — migração 030
-- Fase 10 do PLANO_IMPLEMENTACAO_2026.md: convite assíncrono de
-- colaboradores — docs/ARENA_SPEC.md Fase F, mais H.1
--
-- O que muda: memberships.user_id vira nullable + 6 colunas novas,
-- nenhuma tabela nova. membership_audit_log ganha 3 valores novos de
-- 'acao' (mesmo padrão da migração 024, que já ampliou esse CHECK pra
-- parceria) — sem coluna nova ali.
--
--   memberships.user_id  — DROP NOT NULL. Convite pendente nasce sem
--     usuário resolvido (o problema que a Fase F existe pra resolver:
--     convidar alguém que nunca logou antes) — só é preenchido no
--     aceite.
--   memberships.status    — 'pending' | 'active' | 'cancelled', NOT
--     NULL, default 'active'. 3 estados, não só 'pending' isolado —
--     ver decisão #2 no PLANO_IMPLEMENTACAO_2026.md Fase 10: cancelar
--     precisa de um estado terminal próprio pra não quebrar a
--     invariante "todo pending tem token_hash preenchido".
--   memberships.email       — e-mail convidado (só preenchido em
--     status='pending'/'cancelled' — todo membership pré-existente,
--     que nasce direto 'active', não tem).
--   memberships.invited_by  — quem convidou (FK users, ON DELETE
--     SET NULL — perder o rastro de quem convidou não deveria quebrar
--     a linha se a conta do convidador for anonimizada depois).
--   memberships.token_hash  — SHA-256 do token de aceite, nunca texto
--     puro (mesmo padrão de magic_link_tokens). Único enquanto não
--     nulo.
--   memberships.expires_at  — expira em 7 dias da criação (F.4),
--     calculado em código, não em DEFAULT (mesmo padrão de
--     magic_link_tokens.expira_em).
--   memberships.accepted_at — carimbo de quando foi aceito. Mantido
--     como registro histórico mesmo depois do aceite (status vira
--     'active') — só token_hash é zerado no aceite, pra invalidar o
--     link (mesmo padrão de magic_link_tokens.usado_em).
--
-- É reversível? Sim — 6x DROP COLUMN + user_id volta a NOT NULL
-- desfaz, sem efeito colateral em outra tabela (nenhuma FK aponta pra
-- essas colunas). DROP NOT NULL em user_id só é reversível de volta
-- enquanto não houver linha com user_id NULL no momento do rollback
-- (ou seja: só decidir reverter antes de ter convite pendente real).
-- Afeta dado existente? Nenhum UPDATE necessário — toda linha
-- existente já é o que status='active' DEFAULT descreve (membership
-- concedido direto, sem convite), e user_id já vem preenchido nelas.
-- ============================================================

-- ── 1. memberships.user_id vira nullable ───────────────────────────
ALTER TABLE memberships ALTER COLUMN user_id DROP NOT NULL;

-- ── 2. status + colunas de convite ──────────────────────────────────
ALTER TABLE memberships
  ADD COLUMN IF NOT EXISTS status      text NOT NULL DEFAULT 'active'
    CHECK (status IN ('pending', 'active', 'cancelled')),
  ADD COLUMN IF NOT EXISTS email       text,
  ADD COLUMN IF NOT EXISTS invited_by  uuid REFERENCES users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS token_hash  text,
  ADD COLUMN IF NOT EXISTS expires_at  timestamptz,
  ADD COLUMN IF NOT EXISTS accepted_at timestamptz;

-- Invariante de forma por estado: 'active' sempre tem user_id;
-- 'pending' nunca tem user_id ainda, sempre tem o necessário pra
-- validar o token, e nunca está concedido (ativo=false). 'cancelled'
-- só exige não ter user_id nem token utilizável — email/invited_by
-- ficam de registro histórico, não são obrigatórios reter.
ALTER TABLE memberships ADD CONSTRAINT memberships_status_shape_check CHECK (
  (status = 'active'    AND user_id IS NOT NULL) OR
  (status = 'pending'   AND user_id IS NULL AND ativo = false
                        AND email IS NOT NULL AND token_hash IS NOT NULL
                        AND expires_at IS NOT NULL) OR
  (status = 'cancelled' AND user_id IS NULL AND ativo = false)
);

COMMENT ON COLUMN memberships.status IS
  'active = vínculo concedido de sempre (fluxo direto, inalterado).
   pending = convite assíncrono aguardando aceite — token_hash sempre
   preenchido e utilizável enquanto neste estado (ARENA_SPEC.md F.3).
   cancelled = convite pendente cancelado antes do aceite, nunca
   DELETE físico (F.6).';

COMMENT ON COLUMN memberships.token_hash IS
  'SHA-256 do token de aceite enviado por e-mail — nunca texto puro
   (mesmo padrão de magic_link_tokens.token_hash). Zerado no aceite ou
   no cancelamento, pra invalidar o link mesmo que o e-mail já tenha
   saído (ARENA_SPEC.md F.4).';

-- Único enquanto não nulo — múltiplos convites cancelados/aceitos com
-- token_hash NULL nunca colidem entre si (NULL não é igual a NULL em
-- índice único do Postgres).
CREATE UNIQUE INDEX IF NOT EXISTS idx_memberships_token_hash
  ON memberships(token_hash) WHERE token_hash IS NOT NULL;

-- Fila de convites pendentes de uma Arena (listagem no painel) e
-- contagem de rate limit (H.1) batem no mesmo índice.
CREATE INDEX IF NOT EXISTS idx_memberships_pending_arena
  ON memberships(arena_id, criado_em) WHERE status = 'pending';

-- ── 3. membership_audit_log: 3 novas ações (mesmo padrão da migração
-- 024, que já ampliou este CHECK pra parceria) ──────────────────────
ALTER TABLE membership_audit_log DROP CONSTRAINT IF EXISTS membership_audit_log_acao_check;
ALTER TABLE membership_audit_log ADD CONSTRAINT membership_audit_log_acao_check
  CHECK (acao IN (
    'concedido', 'revogado', 'titularidade_transferida',
    'parceria_liberada', 'parceria_aceita', 'parceria_revogada',
    'convite_enviado', 'convite_cancelado', 'convite_aceito'
  ));
