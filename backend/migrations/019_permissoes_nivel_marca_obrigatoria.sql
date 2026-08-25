-- ============================================================
-- Retro Score Ranking — migração 019
-- Permissões: nível admin/moderador, marca obrigatória, titularidade
--
-- Especificação completa: docs/PERMISSOES_SPEC.md
--
-- Pré-requisitos confirmados em produção antes de escrever esta
-- migração (leitura, sem alterar nada):
--   - SELECT COUNT(*) FROM eventos WHERE marca_id IS NULL  →  0 (de 2 eventos totais)
--   - SELECT COUNT(*) FROM admin_vinculos WHERE escopo = 'evento'  →  0
-- Ambos os pré-requisitos do PERMISSOES_SPEC.md §6/§7 estão satisfeitos:
-- é seguro tornar eventos.marca_id NOT NULL e remover escopo='evento'
-- sem precisar migrar/backfillar nenhum dado real.
--
-- Nota (aprendida nas migrations 011-014): toda tabela nova com RLS
-- precisa de policy explícita 'app_user_all' pro app_user — RLS sem
-- policy bloqueia SILENCIOSAMENTE todo SELECT/INSERT/UPDATE (zero
-- linhas, sem erro). admin_vinculos_auditoria já nasce com a policy.
-- ============================================================

-- ── 1. admin_vinculos: adiciona nivel ──────────────────────────────
ALTER TABLE admin_vinculos
  ADD COLUMN IF NOT EXISTS nivel text CHECK (nivel IN ('admin', 'moderador'));

COMMENT ON COLUMN admin_vinculos.nivel IS
  'NULL quando escopo=''super'' (enxerga/administra tudo, sem nível). '
  'Obrigatório quando escopo=''marca'': admin (controle completo da '
  'marca e dos eventos dela) ou moderador (só modera pontuações, não '
  'cria/edita nada). Nível cascateia da marca pra todos os eventos '
  'dela — não existe nível fino por evento. Ver docs/PERMISSOES_SPEC.md §2.';

-- Backfill defensivo — produção não tem nenhum vínculo escopo='marca'
-- hoje (só 1 vínculo, escopo='super'), mas cobre o caso geral.
UPDATE admin_vinculos SET nivel = 'admin' WHERE escopo = 'marca' AND nivel IS NULL;

-- ── 2. admin_vinculos: remove escopo='evento' e a coluna evento_id ──
-- Confirmado acima: zero vínculos com escopo='evento' em produção —
-- não há dado a migrar. evento_id sai da tabela por completo (decisão
-- #4/#6 do PERMISSOES_SPEC.md): todo evento agora tem marca_id
-- obrigatório, então "vínculo direto a um evento específico" deixou
-- de fazer sentido como conceito.
DROP INDEX IF EXISTS idx_admin_vinculos_unico;
ALTER TABLE admin_vinculos DROP CONSTRAINT IF EXISTS admin_vinculos_check;
ALTER TABLE admin_vinculos DROP CONSTRAINT IF EXISTS admin_vinculos_escopo_check;
ALTER TABLE admin_vinculos DROP COLUMN IF EXISTS evento_id;

ALTER TABLE admin_vinculos
  ADD CONSTRAINT admin_vinculos_escopo_check CHECK (escopo IN ('super', 'marca'));

-- Nome explícito diferente de admin_vinculos_nivel_check: esse nome já
-- foi tomado pelo CHECK inline da própria coluna nivel (auto-nomeado
-- pelo Postgres como <tabela>_<coluna>_check).
ALTER TABLE admin_vinculos
  ADD CONSTRAINT admin_vinculos_escopo_nivel_check CHECK (
    (escopo = 'super' AND nivel IS NULL) OR
    (escopo = 'marca' AND nivel IS NOT NULL AND marca_id IS NOT NULL)
  );

CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_vinculos_unico
  ON admin_vinculos (user_id, escopo, COALESCE(marca_id, '00000000-0000-0000-0000-000000000000'));

-- ── 3. eventos.marca_id vira obrigatório ────────────────────────────
ALTER TABLE eventos ALTER COLUMN marca_id SET NOT NULL;

-- ── 4. marcas.dono_user_id (titularidade) ───────────────────────────
ALTER TABLE marcas
  ADD COLUMN IF NOT EXISTS dono_user_id uuid REFERENCES users(id) ON DELETE SET NULL;

COMMENT ON COLUMN marcas.dono_user_id IS
  'Titular da marca — NÃO é super-admin, é um atributo aplicado sobre '
  'um vínculo admin_vinculos comum (escopo=marca, nivel=admin) dessa '
  'mesma pessoa na mesma marca. Nasce NULL em todas as marcas '
  'existentes — precisa ser atribuído manualmente por um super depois '
  'desta migração, não é inferido de nenhum dado existente. Revogar o '
  'vínculo admin_vinculos do dono_user_id é bloqueado EM CÓDIGO (não '
  'dá pra expressar em CHECK — depende de estado combinado entre '
  'marcas e admin_vinculos): precisa transferir titularidade primeiro. '
  'Ver docs/PERMISSOES_SPEC.md §3.';

-- ── 5. admin_vinculos_auditoria (nova tabela) ────────────────────────
CREATE TABLE IF NOT EXISTS admin_vinculos_auditoria (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  acao          text        NOT NULL CHECK (acao IN ('concedido', 'revogado', 'titularidade_transferida')),
  marca_id      uuid        REFERENCES marcas(id) ON DELETE CASCADE,
  user_alvo_id  uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  realizado_por text        NOT NULL,
  nivel         text,
  detalhes      jsonb,
  criado_em     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE admin_vinculos_auditoria IS
  'Log de toda concessão/revogação/transferência de admin_vinculos — '
  'geral, não só titularidade (decisão #12 do PERMISSOES_SPEC.md). '
  'Nunca editável nem apagável pelo app_user (só INSERT) — é log, não '
  'estado.';

COMMENT ON COLUMN admin_vinculos_auditoria.marca_id IS
  'NULL quando a ação envolve escopo=''super'' (concessão/revogação de '
  'super-admin não tem marca associada).';

COMMENT ON COLUMN admin_vinculos_auditoria.realizado_por IS
  'Identificador de quem realizou a ação — mesmo padrão de '
  'moderado_por/criado_por já usado no projeto (email ou "admin" pro '
  'bootstrap via ADMIN_SECRET).';

COMMENT ON COLUMN admin_vinculos_auditoria.nivel IS
  'Nível envolvido na ação (admin/moderador), quando aplicável — NULL '
  'para ações de escopo=super ou transferência de titularidade.';

CREATE INDEX IF NOT EXISTS idx_admin_vinculos_auditoria_marca
  ON admin_vinculos_auditoria(marca_id);
CREATE INDEX IF NOT EXISTS idx_admin_vinculos_auditoria_user_alvo
  ON admin_vinculos_auditoria(user_alvo_id);

-- ── 6. RLS + policy (já nasce configurado, não depois) ───────────────
ALTER TABLE admin_vinculos_auditoria ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'admin_vinculos_auditoria' AND policyname = 'app_user_all'
  ) THEN
    CREATE POLICY app_user_all ON admin_vinculos_auditoria
      FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;

-- Sem DELETE/UPDATE pro app_user nesta tabela — é log, é só INSERT +
-- SELECT (mesmo padrão de "ativo=false em vez de DELETE" levado ao
-- extremo: aqui nem UPDATE existe).
GRANT SELECT, INSERT ON admin_vinculos_auditoria TO app_user;
