-- ============================================================
-- Retro Score Ranking — migração 016
-- Marcas (identidade visual acima de evento) + campos de herança
--
-- Especificação completa: docs/MARCAS_SPEC.md
--
-- Precedência de resolução (aplicada no backend, não no schema):
--   cor_primaria / tipografia / logo_url:
--     eventos.<campo>  →  marcas.<campo> (via eventos.marca_id)  →  default da plataforma
--
-- Nota (aprendida nas migrations 011-014): toda tabela nova com RLS
-- precisa de policy explícita 'app_user_all' pro app_user — RLS sem
-- policy bloqueia SILENCIOSAMENTE todo SELECT/INSERT/UPDATE (zero
-- linhas, sem erro). Esta migração já nasce com a policy.
-- ============================================================

-- ── 1. Tabela marcas ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS marcas (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  nome          text        NOT NULL,
  slug          text        UNIQUE NOT NULL,
  cor_primaria  text,
  tipografia    text        CHECK (tipografia IN ('arcade', 'futurista', 'terminal')),
  logo_url      text,
  criado_em     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE marcas IS
  'Nível de identidade visual acima de evento. Um evento pode herdar '
  'cor_primaria, tipografia e logo_url de sua marca — ver docs/MARCAS_SPEC.md.';

COMMENT ON COLUMN marcas.cor_primaria IS
  'Hex, ex. #5e2b82. NULL = marca não define cor própria.';

COMMENT ON COLUMN marcas.tipografia IS
  'Um de: arcade (Press Start 2P, default da plataforma), futurista '
  '(Orbitron), terminal (Share Tech Mono). NULL = sem preferência da marca.';

COMMENT ON COLUMN marcas.logo_url IS
  'Logo da marca. Serve de fallback para eventos sem logo_url próprio '
  '(mesma cadeia de herança de cor_primaria/tipografia).';

-- ── 2. eventos ganha marca_id e tipografia ─────────────────────────
ALTER TABLE eventos
  ADD COLUMN IF NOT EXISTS marca_id   uuid REFERENCES marcas(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS tipografia text CHECK (tipografia IN ('arcade', 'futurista', 'terminal'));

COMMENT ON COLUMN eventos.marca_id IS
  'Marca vinculada (opcional). Apagar a marca não apaga o evento — só '
  'desvincula (ON DELETE SET NULL).';

COMMENT ON COLUMN eventos.tipografia IS
  'Override da tipografia da marca, mesmo padrão de logo_url/cor_primaria '
  'já existentes nesta tabela. NULL = herda da marca (se houver) ou do '
  'default da plataforma.';

CREATE INDEX IF NOT EXISTS idx_eventos_marca ON eventos(marca_id)
  WHERE marca_id IS NOT NULL;

-- ── 3. RLS + policy (já nasce configurado, não depois) ─────────────
ALTER TABLE marcas ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'marcas' AND policyname = 'app_user_all'
  ) THEN
    CREATE POLICY app_user_all ON marcas
      FOR ALL TO app_user USING (true) WITH CHECK (true);
  END IF;
END $$;

-- ── 4. Permissões para app_user ────────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON marcas TO app_user;
