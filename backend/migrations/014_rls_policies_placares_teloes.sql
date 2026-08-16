-- ============================================================
-- Retro Score Ranking — migração 014
-- Policies de RLS para app_user nas tabelas novas (placares, teloes)
--
-- Diagnóstico: entradas, jogos, eventos, evento_config e evento_jogos
-- têm uma policy 'app_user_all' (PERMISSIVE, FOR ALL, USING true,
-- WITH CHECK true) criada diretamente no Supabase, fora de qualquer
-- migration versionada. As 4 tabelas novas da migration 011
-- (placares, placar_eventos, teloes, telao_jogos) nunca ganharam essa
-- policy — RLS habilitado sem policy bloqueia SILENCIOSAMENTE todo
-- SELECT/INSERT/UPDATE do app_user (sem erro, só "0 linhas"), que foi
-- exatamente o sintoma observado: GET /api/teloes/geral/config
-- retornando 404 mesmo com a linha existindo de verdade no banco.
--
-- Esta migração formaliza o mesmo padrão em código versionado, pra
-- não depender de configuração manual não documentada no futuro.
-- Idempotente via checagem em pg_policies.
-- ============================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'placares' AND policyname = 'app_user_all'
  ) THEN
    CREATE POLICY app_user_all ON placares
      FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'placar_eventos' AND policyname = 'app_user_all'
  ) THEN
    CREATE POLICY app_user_all ON placar_eventos
      FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'teloes' AND policyname = 'app_user_all'
  ) THEN
    CREATE POLICY app_user_all ON teloes
      FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'telao_jogos' AND policyname = 'app_user_all'
  ) THEN
    CREATE POLICY app_user_all ON telao_jogos
      FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;
