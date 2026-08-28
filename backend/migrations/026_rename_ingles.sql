-- ============================================================
-- Retro Score Ranking — migração 026
-- Fase 7 do PLANO_IMPLEMENTACAO_2026.md: rename retroativo de
-- identificadores de código pra inglês (decisão cross-cutting
-- registrada em docs/ARENA_SPEC.md §5)
--
-- O que muda: renomeia 7 tabelas e as colunas/índices/constraints
-- que carregam os mesmos nomes no corpo:
--   marcas                  → arenas
--   admin_vinculos          → memberships
--   admin_vinculos_auditoria → membership_audit_log
--   entradas                → entries
--   eventos                 → events
--   jogos                   → games
--   marcas_parcerias        → arena_partnerships
--
--   marcas.dono_user_id            → arenas.owner_user_id
--   admin_vinculos.escopo          → memberships.scope
--   admin_vinculos.nivel           → memberships.role
--   admin_vinculos.marca_id        → memberships.arena_id
--   admin_vinculos_auditoria.marca_id → membership_audit_log.arena_id
--   eventos.marca_id               → events.arena_id
--   entradas.evento_id             → entries.event_id
--   entradas.jogo_id               → entries.game_id
--   jogos.mesclado_em_jogo_id      → games.mesclado_em_game_id
--   marcas_parcerias.marca_origem_id  → arena_partnerships.arena_origem_id
--   marcas_parcerias.marca_destino_id → arena_partnerships.arena_destino_id
--
-- É reversível? Sim — cada ALTER TABLE ... RENAME TO / RENAME COLUMN
-- pode ser desfeito com o rename inverso, na ordem contrária. Nenhum
-- DROP, nenhum DELETE, nenhuma linha tocada.
-- Afeta dado existente? As LINHAS não mudam — é rename de metadado de
-- schema (nome de tabela/coluna/índice/constraint), não de conteúdo.
-- O CONTEÚDO das colunas (valores como escopo='marca', modo_ranking=
-- 'marca'/'marca_parceiras'/'ultimo_evento') NÃO muda nesta migração —
-- só o nome das colunas/tabelas que os guardam. O backend novo (Fase 7)
-- já foi escrito esperando esse contrato: código compara contra os
-- MESMOS valores Portugueses ('marca', 'super', 'marca_parceiras',
-- 'ultimo_evento', 'zerado', 'geral') — só os nomes de tabela/coluna
-- em volta mudaram.
--
-- Fora de escopo, propositalmente intocado (ARENA_SPEC.md §5): as
-- tabelas placares, placar_eventos, teloes, telao_jogos, seguidores,
-- nick_claims, avatares, users e todas as suas colunas — inclusive
-- teloes.evento_id, placar_eventos.evento_id e telao_jogos.jogo_id,
-- que continuam em português mesmo referenciando conceitos renomeados
-- (events/games) via FK. RLS: RENAME TABLE no Postgres carrega a
-- policy junto automaticamente (a policy é ligada por OID, não por
-- nome) — não precisa recriar 'app_user_all' em nenhuma das 7 tabelas.
--
-- Pré-requisito antes de rodar: nenhum — rename puro, sem backfill,
-- sem auditoria de dado órfão necessária (diferente da migração 019).
-- ============================================================

-- ── 1. Rename das 7 tabelas ─────────────────────────────────────
ALTER TABLE marcas                   RENAME TO arenas;
ALTER TABLE admin_vinculos_auditoria RENAME TO membership_audit_log;
ALTER TABLE admin_vinculos           RENAME TO memberships;
ALTER TABLE entradas                 RENAME TO entries;
ALTER TABLE eventos                  RENAME TO events;
ALTER TABLE jogos                    RENAME TO games;
ALTER TABLE marcas_parcerias         RENAME TO arena_partnerships;

-- ── 2. Rename de colunas ────────────────────────────────────────
ALTER TABLE arenas  RENAME COLUMN dono_user_id TO owner_user_id;

ALTER TABLE memberships RENAME COLUMN escopo   TO scope;
ALTER TABLE memberships RENAME COLUMN nivel    TO role;
ALTER TABLE memberships RENAME COLUMN marca_id TO arena_id;

ALTER TABLE membership_audit_log RENAME COLUMN marca_id TO arena_id;

ALTER TABLE events RENAME COLUMN marca_id TO arena_id;

ALTER TABLE entries RENAME COLUMN evento_id TO event_id;
ALTER TABLE entries RENAME COLUMN jogo_id   TO game_id;

ALTER TABLE games RENAME COLUMN mesclado_em_jogo_id TO mesclado_em_game_id;

ALTER TABLE arena_partnerships RENAME COLUMN marca_origem_id  TO arena_origem_id;
ALTER TABLE arena_partnerships RENAME COLUMN marca_destino_id TO arena_destino_id;

-- ── 3. Rename de índices e constraints nomeados (cosmético — não
--       afeta comportamento, evita ficar com "idx_marcas_parcerias_*"
--       apontando pra uma tabela chamada arena_partnerships) ────────
ALTER INDEX IF EXISTS idx_entradas_evento              RENAME TO idx_entries_event;
ALTER INDEX IF EXISTS idx_evento_jogos_evento           RENAME TO idx_event_games_event;
ALTER INDEX IF EXISTS idx_entradas_evento_jogo          RENAME TO idx_entries_event_game;
ALTER INDEX IF EXISTS idx_eventos_marca                 RENAME TO idx_events_arena;
ALTER INDEX IF EXISTS idx_admin_vinculos_unico          RENAME TO idx_memberships_unico;
ALTER INDEX IF EXISTS idx_admin_vinculos_user           RENAME TO idx_memberships_user;
ALTER INDEX IF EXISTS idx_jogos_pendente                RENAME TO idx_games_pendente;
ALTER INDEX IF EXISTS idx_admin_vinculos_auditoria_marca     RENAME TO idx_membership_audit_log_arena;
ALTER INDEX IF EXISTS idx_admin_vinculos_auditoria_user_alvo RENAME TO idx_membership_audit_log_user_alvo;
ALTER INDEX IF EXISTS idx_marcas_parcerias_destino      RENAME TO idx_arena_partnerships_destino;
ALTER INDEX IF EXISTS idx_marcas_parcerias_origem       RENAME TO idx_arena_partnerships_origem;

ALTER TABLE memberships RENAME CONSTRAINT admin_vinculos_escopo_check       TO memberships_scope_check;
ALTER TABLE memberships RENAME CONSTRAINT admin_vinculos_escopo_nivel_check TO memberships_scope_role_check;
ALTER TABLE membership_audit_log RENAME CONSTRAINT admin_vinculos_auditoria_acao_check TO membership_audit_log_acao_check;
ALTER TABLE arena_partnerships   RENAME CONSTRAINT marcas_parcerias_nao_a_si_mesma      TO arena_partnerships_nao_a_si_mesma;

-- Tabela evento_jogos (junção entre events e games, DENTRO do escopo
-- desta fase — não confundir com telao_jogos/placar_eventos, que são
-- fora de escopo e continuam intocadas):
ALTER TABLE evento_jogos RENAME TO event_games;
ALTER TABLE event_games  RENAME COLUMN evento_id TO event_id;
ALTER TABLE event_games  RENAME COLUMN jogo_id   TO game_id;
