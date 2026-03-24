-- Retro Score Ranking — migração 009
-- Cria tabela de eventos e associa entradas existentes

-- Tabela de eventos
CREATE TABLE IF NOT EXISTS eventos (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  nome        text        NOT NULL,
  slug        text        UNIQUE NOT NULL,
  ativo       boolean     NOT NULL DEFAULT true,
  data_inicio timestamptz NOT NULL DEFAULT now(),
  data_fim    timestamptz,
  criado_em   timestamptz NOT NULL DEFAULT now()
);

-- Evento padrão para scores já existentes
INSERT INTO eventos (nome, slug, ativo)
VALUES ('Evento Padrão', 'padrao', false)
ON CONFLICT (slug) DO NOTHING;

-- FK em entradas (nullable — scores antigos ficam sem evento até associação manual)
ALTER TABLE entradas ADD COLUMN IF NOT EXISTS evento_id uuid REFERENCES eventos(id);

-- Índice para filtrar por evento
CREATE INDEX IF NOT EXISTS idx_entradas_evento ON entradas(evento_id)
  WHERE evento_id IS NOT NULL;
