-- ============================================================
-- Retro Score Ranking — migração 025
-- Fase 4: admin_vinculos_auditoria.user_alvo_id passa a aceitar NULL
--
-- Achado ao implementar os endpoints de parceria entre marcas
-- (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2 decisão #6): a auditoria de
-- parceria grava o próprio ator (quem clicou) em user_alvo_id — mas o
-- ator pode ser o bootstrap via Bearer <ADMIN_SECRET>, que não tem
-- user_id (AdminContext.user_id = None nesse caminho, ver
-- middleware/auth.py). A coluna nasceu NOT NULL na migration 019,
-- porque até aqui toda ação auditada (conceder/revogar vínculo,
-- transferir titularidade) sempre tinha um USUÁRIO ALVO real e
-- diferente do ator. Parceria é a primeira ação onde o "alvo" é o
-- próprio ator — mesma categoria de gap já corrigida uma vez na
-- migration 022 (nick_troca_forcada_auditoria.nick_anterior).
--
-- Puramente aditiva/permissiva — não apaga nem altera nenhuma linha
-- existente, só relaxa a constraint. Reversível (poderia voltar a
-- NOT NULL se todas as linhas existentes continuarem preenchidas).
-- ============================================================

ALTER TABLE admin_vinculos_auditoria ALTER COLUMN user_alvo_id DROP NOT NULL;

COMMENT ON COLUMN admin_vinculos_auditoria.user_alvo_id IS
  'Usuário alvo da ação (quem ganhou/perdeu vínculo, ou o novo titular).
  NULL quando a ação não tem um alvo diferente do ator — caso de
  parceria entre marcas acionada via bootstrap (Bearer <ADMIN_SECRET>,
  sem user_id de sessão real); nesse caso realizado_por="admin" já
  identifica quem agiu.';
