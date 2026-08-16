-- ============================================================
-- Retro Score Ranking — migração 011
-- Placares (geral + customizados), telões como entidade própria,
-- janela de envio obrigatória, entradas.evento_id obrigatório
--
-- Especificação completa: docs/EVENTOS_SPEC.md
-- ============================================================

-- ── 1. eventos.data_fim vira obrigatório ───────────────────────
-- Popula eventos existentes sem data_fim com um horizonte distante
-- (sinaliza "sem previsão de encerramento" sem precisar de NULL
-- especial no schema — ver EVENTOS_SPEC.md §3).
UPDATE eventos
SET data_fim = now() + interval '10 years'
WHERE data_fim IS NULL;

ALTER TABLE eventos
  ALTER COLUMN data_fim SET NOT NULL;

COMMENT ON COLUMN eventos.data_fim IS
  'Fim da janela de ENVIO de novos scores. Não afeta visibilidade — '
  'ver coluna publico. Evento pode ficar publico=true para sempre '
  'mesmo com data_fim no passado.';

COMMENT ON COLUMN eventos.data_inicio IS
  'Início da janela de ENVIO de novos scores.';

-- ── 2. Tabela placares ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS placares (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  nome       text        NOT NULL,
  slug       text        UNIQUE NOT NULL,
  escopo     text        NOT NULL CHECK (escopo IN ('global', 'customizado')),
  criado_em  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE placares IS
  'Escopo de ranking além do por-evento. escopo=global inclui todos os '
  'eventos (presentes e futuros) sem precisar de linha em placar_eventos. '
  'escopo=customizado usa placar_eventos para membership curada.';

-- Garante um único placar global
CREATE UNIQUE INDEX IF NOT EXISTS idx_placares_unico_global
  ON placares ((escopo = 'global'))
  WHERE escopo = 'global';

-- Semeia o placar global
INSERT INTO placares (nome, slug, escopo)
VALUES ('Hall da Fama Geral', 'geral', 'global')
ON CONFLICT (slug) DO NOTHING;

-- ── 3. Tabela placar_eventos (N:N, só para escopo=customizado) ──
CREATE TABLE IF NOT EXISTS placar_eventos (
  placar_id  uuid        NOT NULL REFERENCES placares(id) ON DELETE CASCADE,
  evento_id  uuid        NOT NULL REFERENCES eventos(id)  ON DELETE CASCADE,
  criado_em  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (placar_id, evento_id)
);

COMMENT ON TABLE placar_eventos IS
  'Membership curada manualmente pelo admin. Eventos novos NÃO entram '
  'automaticamente num placar customizado.';

CREATE INDEX IF NOT EXISTS idx_placar_eventos_placar
  ON placar_eventos(placar_id);

-- ── 4. Tabela teloes ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teloes (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  nome       text        NOT NULL,
  slug       text        UNIQUE NOT NULL,
  evento_id  uuid        REFERENCES eventos(id)  ON DELETE CASCADE,
  placar_id  uuid        REFERENCES placares(id) ON DELETE CASCADE,
  top_n      int         NOT NULL DEFAULT 10 CHECK (top_n > 0),
  criado_em  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT teloes_evento_ou_placar CHECK (
    (evento_id IS NOT NULL) != (placar_id IS NOT NULL)
  )
);

COMMENT ON TABLE teloes IS
  'Tela de exibição configurável. Aponta para exatamente um evento OU um '
  'placar (nunca os dois, nunca nenhum). top_n = posições fixas exibidas, '
  'sem paginação (EVENTOS_SPEC.md §5).';

CREATE INDEX IF NOT EXISTS idx_teloes_evento  ON teloes(evento_id)  WHERE evento_id  IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_teloes_placar  ON teloes(placar_id)  WHERE placar_id  IS NOT NULL;

-- Semeia o telão "Hall da Fama Geral" apontando pro placar global,
-- preservando o comportamento atual do telao.html (top 10)
INSERT INTO teloes (nome, slug, placar_id, top_n)
SELECT 'Hall da Fama Geral', 'geral', p.id, 10
FROM placares p
WHERE p.slug = 'geral'
ON CONFLICT (slug) DO NOTHING;

-- ── 5. Tabela telao_jogos ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS telao_jogos (
  telao_id   uuid        NOT NULL REFERENCES teloes(id) ON DELETE CASCADE,
  jogo_id    uuid        NOT NULL REFERENCES jogos(id)  ON DELETE RESTRICT,
  ordem      int         NOT NULL DEFAULT 0,
  ativo      boolean     NOT NULL DEFAULT true,
  criado_em  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (telao_id, jogo_id)
);

COMMENT ON TABLE telao_jogos IS
  'Cada telão escolhe seus próprios jogos e ordem, independente de '
  'evento_jogos (EVENTOS_SPEC.md §3, decisão #4).';

CREATE INDEX IF NOT EXISTS idx_telao_jogos_telao
  ON telao_jogos(telao_id) WHERE ativo = true;

-- Popula o telão "Hall da Fama Geral" com todos os jogos hoje ativos,
-- na mesma ordem alfabética que listar_ativos já usa (ORDER BY nome) —
-- ponto de partida idêntico ao comportamento atual do telao.html.
INSERT INTO telao_jogos (telao_id, jogo_id, ordem, ativo)
SELECT
  t.id,
  j.id,
  ROW_NUMBER() OVER (ORDER BY j.nome) - 1,
  true
FROM teloes t
CROSS JOIN jogos j
WHERE t.slug = 'geral'
  AND j.ativo = true
ON CONFLICT (telao_id, jogo_id) DO NOTHING;

-- ── 6. entradas.evento_id vira obrigatório ───────────────────────
-- Seguro: a Migration 010 já garantiu que não existem linhas com
-- evento_id IS NULL (todas foram associadas ao canal3expo).
ALTER TABLE entradas
  ALTER COLUMN evento_id SET NOT NULL;

-- ── 7. RLS nas tabelas novas ──────────────────────────────────────
ALTER TABLE placares       ENABLE ROW LEVEL SECURITY;
ALTER TABLE placar_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE teloes         ENABLE ROW LEVEL SECURITY;
ALTER TABLE telao_jogos    ENABLE ROW LEVEL SECURITY;

-- ── 8. Permissões para app_user ───────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON placares       TO app_user;
GRANT SELECT, INSERT, UPDATE ON placar_eventos TO app_user;
GRANT SELECT, INSERT, UPDATE ON teloes         TO app_user;
GRANT SELECT, INSERT, UPDATE ON telao_jogos    TO app_user;
