-- ============================================================
-- Retro Score Ranking — migração 028
-- Fase 8 do PLANO_IMPLEMENTACAO_2026.md: fundação Arena self-serve
-- (admissão, dados, cadastro) — docs/ARENA_SPEC.md Fases B, C, D, G
--
-- O que muda: 3 colunas novas, nenhuma tabela nova.
--
--   arenas.status    — 'draft' | 'published' | 'suspended', NOT NULL,
--     default 'published'. Controla só descoberta por estranho (B.1):
--     Arena 'draft' funciona normal pra quem já tem acesso, só não
--     aparece em listagem/diretório público até um super aprovar
--     (heurística de risco B.4) ou nasce 'published' direto quando não
--     dispara nenhum sinal de risco (C.1). 'suspended' é congelamento
--     pós-hoc de Arena já pública, se abuso for confirmado depois.
--   arenas.plan      — texto livre, NOT NULL, default 'free'. Só
--     'free' existe hoje — sem CHECK de valores permitidos de
--     propósito, não há tier paga desenhada ainda pra travar contra
--     (C.2, decisão explícita de não superengenheirar).
--   events.visibility — 'open' | 'private', NOT NULL, default
--     'private'. Eixo independente de events.publico (que já existe e
--     controla acesso via link direto) — visibility controla só
--     aparecer em diretório de busca (D.7). Default 'private' porque
--     grupo caseiro não deve ser surpreendido aparecendo num
--     diretório público sem pedir.
--
-- Pré-requisito (G.1) já resolvido antes desta migração, fora dela:
-- as 2 Arenas legadas (Canal3, Old School Pinball) tinham
-- owner_user_id nulo — titularidade atribuída manualmente via
-- repositório real do app (não SQL direto), registrado no
-- PLANO_IMPLEMENTACAO_2026.md.
--
-- É reversível? Sim — 3x DROP COLUMN desfaz, sem efeito colateral em
-- nenhuma outra tabela (nenhuma FK aponta pra essas colunas).
-- Afeta dado existente? Dois UPDATEs explícitos, os dois pelo mesmo
-- motivo (G.1 — Arena/event que já existe é conhecido, já roda coisa
-- real, não deveria regredir silenciosamente por causa de um DEFAULT
-- pensado pro cadastro novo):
--   arenas.status  → 'published' explícito pras 2 Arenas existentes.
--   events.visibility → 'open' explícito pros events existentes —
--     sem isso, os events das Arenas legadas sumiriam do diretório de
--     descoberta da home institucional (Fase 8) assim que esta
--     migração rodasse, mesmo já sendo público/conhecido hoje.
-- arenas.plan usa só o DEFAULT da coluna ('free') — não há
-- ambiguidade de "deveria ter nascido diferente" nesse campo.
-- ============================================================

-- ── 1. arenas.status ────────────────────────────────────────────
ALTER TABLE arenas
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'published'
    CHECK (status IN ('draft', 'published', 'suspended'));

UPDATE arenas SET status = 'published' WHERE status IS DISTINCT FROM 'published';

COMMENT ON COLUMN arenas.status IS
  'draft = aguardando revisão de super (heurística de risco B.4),
   published = visível em qualquer diretório/listagem pública,
   suspended = congelada pós-hoc por abuso confirmado. Nunca bloqueia
   funcionalidade pro próprio grupo — só restringe descoberta por
   estranho (ARENA_SPEC.md B.1).';

CREATE INDEX IF NOT EXISTS idx_arenas_status ON arenas(status) WHERE status = 'draft';

-- ── 2. arenas.plan ──────────────────────────────────────────────
ALTER TABLE arenas
  ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'free';

COMMENT ON COLUMN arenas.plan IS
  'Só "free" existe hoje — sem CHECK de valores permitidos de
   propósito (ARENA_SPEC.md C.2), evita migração retroativa quando um
   tier pago for desenhado de verdade.';

-- ── 3. events.visibility ────────────────────────────────────────
ALTER TABLE events
  ADD COLUMN IF NOT EXISTS visibility text NOT NULL DEFAULT 'private'
    CHECK (visibility IN ('open', 'private'));

-- Backfill explícito pros events já existentes (mesmo raciocínio do
-- G.1 pra arenas.status): DEFAULT 'private' é o certo daqui pra
-- frente (D.7 — grupo caseiro não deve ser surpreendido aparecendo
-- num diretório sem pedir), mas os events que já existem hoje são de
-- Arena conhecida, já pública, já rodando — apagar essa
-- descobribilidade de propósito seria regressão silenciosa, não
-- consequência neutra do rename/schema novo. Sem isso, os events das
-- 2 Arenas legadas sumiriam do diretório de descoberta da home
-- institucional (Fase 8) no instante em que essa migração rodasse.
UPDATE events SET visibility = 'open' WHERE visibility IS DISTINCT FROM 'open';

COMMENT ON COLUMN events.visibility IS
  'Eixo independente de events.publico (que controla acesso via link
   direto). visibility controla só aparecer em diretório de busca da
   home institucional — "open" = descoberta ativa, "private" = só quem
   tem o link (ARENA_SPEC.md D.7).';
