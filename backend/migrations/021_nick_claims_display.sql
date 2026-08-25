-- ============================================================
-- Retro Score Ranking — migração 021
-- nick_claims ganha a versão de exibição do nick (só existia nick_norm,
-- normalizado/minúsculo — insuficiente pra perfil mostrar "seu nick
-- atual" ou pré-preencher envios futuros com a grafia original)
--
-- Especificação: docs/NICKNAME_SPEC.md
--
-- Puramente aditiva. nick_claims está vazia em produção (confirmado na
-- migration 020) — NOT NULL direto, sem precisar de nullable+backfill.
-- ============================================================

ALTER TABLE nick_claims ADD COLUMN IF NOT EXISTS nick text NOT NULL;

COMMENT ON COLUMN nick_claims.nick IS
  'Versão de exibição do nick (grafia original, maiúsculas/minúsculas '
  'preservadas) — nick_norm continua sendo o normalizado usado só pra '
  'garantir unicidade. Ausente na migration 015 original (só nick_norm '
  'existia); necessário pra perfil exibir "nick atual" e pré-preencher '
  'envios futuros (BACKLOG_2026.md §2 item 2.3).';
