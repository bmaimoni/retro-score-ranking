-- ============================================================
-- Retro Score Ranking — migração 022
-- nick_troca_forcada_auditoria.nick_anterior vira nullable
--
-- Corrige a migration 020: NOT NULL não cobre o caso de um
-- admin/moderador forçar a PRIMEIRA reivindicação de nick de alguém
-- (sem nick anterior nenhum pra registrar) — caso raro (decisão #9 do
-- NICKNAME_SPEC.md prevê principalmente correção de nick já existente
-- e ofensivo), mas legítimo, e a alternativa (string vazia no lugar de
-- NULL) seria pior qualidade de dado que a coluna aceitar NULL de
-- verdade.
--
-- Tabela nasceu vazia na migration 020 e continua vazia — sem dado a
-- migrar.
-- ============================================================

ALTER TABLE nick_troca_forcada_auditoria ALTER COLUMN nick_anterior DROP NOT NULL;
