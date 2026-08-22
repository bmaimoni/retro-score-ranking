-- ============================================================
-- Retro Score Ranking — migração 017
-- Administração escopada por evento/marca/super-admin (Fase 2)
--
-- Especificação completa: docs/MARCAS_SPEC.md §6
--
-- Substitui o modelo de "um ADMIN_SECRET único vê tudo" por
-- administradores individuais, cada um vinculado a um escopo. O
-- ADMIN_SECRET continua funcionando como bootstrap/emergência
-- (equivalente a super-admin) — não é removido nesta migração.
--
-- Nota (aprendida nas migrations 011-014): toda tabela nova com RLS
-- precisa de policy explícita 'app_user_all' pro app_user — RLS sem
-- policy bloqueia SILENCIOSAMENTE todo SELECT/INSERT/UPDATE. Esta
-- migração já nasce com a policy.
-- ============================================================

CREATE TABLE IF NOT EXISTS admin_vinculos (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  escopo     text        NOT NULL CHECK (escopo IN ('super', 'marca', 'evento')),
  marca_id   uuid        REFERENCES marcas(id)  ON DELETE CASCADE,
  evento_id  uuid        REFERENCES eventos(id) ON DELETE CASCADE,
  ativo      boolean     NOT NULL DEFAULT true,
  criado_em  timestamptz NOT NULL DEFAULT now(),
  CHECK (
    (escopo = 'super'  AND marca_id IS NULL     AND evento_id IS NULL) OR
    (escopo = 'marca'  AND marca_id IS NOT NULL AND evento_id IS NULL) OR
    (escopo = 'evento' AND evento_id IS NOT NULL AND marca_id IS NULL)
  )
);

COMMENT ON TABLE admin_vinculos IS
  'Vincula um usuário (users, mesma tabela de identidade de visitante) a '
  'um escopo de administração. Um usuário pode ter vários vínculos '
  '(ex.: admin de 2 eventos específicos, sem ser admin de nenhuma marca '
  'inteira). Ver docs/MARCAS_SPEC.md §6.';

COMMENT ON COLUMN admin_vinculos.ativo IS
  '"Remover" um vínculo é ativo=false, não DELETE — app_user não tem '
  'essa permissão nesta tabela (mesmo padrão de evento_jogos/'
  'placar_eventos).';

-- Evita vínculo duplicado idêntico (mesmo usuário + mesmo escopo + mesmo alvo)
CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_vinculos_unico
  ON admin_vinculos (user_id, escopo, COALESCE(marca_id, '00000000-0000-0000-0000-000000000000'),
                                       COALESCE(evento_id, '00000000-0000-0000-0000-000000000000'));

CREATE INDEX IF NOT EXISTS idx_admin_vinculos_user ON admin_vinculos(user_id)
  WHERE ativo = true;

-- ── RLS + policy (já nasce configurado) ────────────────────────────
ALTER TABLE admin_vinculos ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'admin_vinculos' AND policyname = 'app_user_all'
  ) THEN
    CREATE POLICY app_user_all ON admin_vinculos
      FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;

-- ── Permissões para app_user (sem DELETE, mesmo padrão do projeto) ──
GRANT SELECT, INSERT, UPDATE ON admin_vinculos TO app_user;
