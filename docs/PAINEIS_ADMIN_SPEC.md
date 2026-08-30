# Painéis Admin: separação Console (super) vs. Painel de Arena, e correção do escopo de jogos por evento

> Status: **em especificação — decisões abertas, nenhuma fechada ainda**.
> Complementa `PERMISSOES_SPEC.md` (regras de nível/escopo, que não mudam
> aqui) e se sobrepõe parcialmente a `CATALOGO_JOGOS_SPEC.md` Fases 2-4
> (painel "Jogos" revisitado pra escala self-serve) — ver §5. Escrito a
> partir de uma queixa concreta do Bruno sobre a experiência de admin
> hoje, não de uma ideia abstrata de reorganizar telas.

---

## 1. Como chegamos aqui

Bruno pediu pra separar as telas de super-admin e de admin de
Arena/evento — hoje `admin.html` é um arquivo único (~3200 linhas) que
serve os dois públicos por cima do mesmo HTML/JS, escondendo elementos
via `display:none`/checagem de `meInfo.super` espalhada em dezenas de
pontos. Motivação declarada: confusão real de UX, dificuldade de manter
o arquivo, e — o motivo mais concreto — **os dois públicos já não
conseguem fazer coisas que deveriam**: super não tem UI pra moderar
Arena/evento, admin de evento não consegue subir logo de verdade nem
gerenciar corretamente os jogos ativos do próprio evento.

Investigando essa última queixa antes de propor qualquer solução visual,
apareceu algo mais sério que "falta polimento": um **bug de escrita
cross-arena** (§2, achado 1) — não é só UX, é isolamento quebrado. Por
isso este documento trata os três achados como uma decisão só: separar
telas sem corrigir o modelo de dados por baixo só esconderia o bug atrás
de uma UI mais bonita.

---

## 2. Achados de implementação (mapeados antes de qualquer decisão nova)

| # | Achado | Evidência | Gravidade |
|---|---|---|---|
| 1 | Toggle "jogo ativo" no painel de Arena mexe no **catálogo global** (`games.ativo`), não no vínculo do evento (`event_games.ativo`) — e o endpoint que ele chama não checa vínculo de arena nenhum | `frontend/admin.html:1647-1656` (toggle chama `PATCH /api/admin/games/{id}`) → `backend/routers/admin.py:384-408` (`atualizar_game`, só bloqueia moderador — não checa **qual** arena) → `backend/repositories/game.py:98-137` (`UPDATE games ... WHERE id=$1`, sem `arena_id`/`event_id` no WHERE) | **Alta — qualquer admin de qualquer Arena desativa ou edita `score_max`/`plataforma`/`capa_url` de um jogo de outra Arena.** Mesma classe de risco do vazamento cross-marca já corrigido em `PERMISSOES_SPEC.md` §8.1, só que em escrita, não leitura |
| 2 | O endpoint certo, já escopado corretamente por arena, **existe e nunca é usado** pelo painel | `backend/routers/events.py:153-205` (`GET/POST/PATCH /api/admin/events/{id}/games`, com `_exigir_admin_na_arena` — checa `event["arena_id"]` de verdade) | Achado positivo — não precisa desenhar nada novo no backend pra essa parte, só religar o frontend |
| 3 | "Logo" da Arena é `<input type="text">` pedindo URL, nunca upload de arquivo — apesar de já existir infraestrutura de upload de imagem no projeto | `frontend/admin.html:882` (`placeholder="Logo (ex: ... ou URL completa)"`) vs. `backend/services/storage.py` (`upload_foto`, usado hoje só pra foto de evidência de score em `event_public.py:233`) | Média — fricção real no aha-moment self-serve (`ARENA_SPEC.md` E.2), não é bug de segurança |
| 4 | Super já tem endpoints de moderação de Arena (fila de revisão, suspensão), mas **nenhuma UI** os expõe | `backend/routers/arenas_admin.py:234-270` (`GET fila-revisao`, `PATCH .../aprovar`, `PATCH .../suspender`) — zero referência a `suspender`/`fila`/`revisao`/`draft` em `frontend/admin.html` | Média hoje (só 2 arenas publicadas, 0 em draft — confirmado em produção), sobe de gravidade conforme self-serve crescer |
| 5 | Aba "Manutenção" (limpar/restaurar ranking, config de telão) aparece pra **qualquer** admin, mas a ação de limpeza é super-only no backend — 403 silencioso na cara de admin de Arena | `frontend/admin.html:761-762` (botão da aba sem `style="display:none"` condicional, diferente de wizard/administradores/exclusões que já escondem) vs. `backend/routers/admin.py:540-548` (`_exigir_super_manutencao`) | Baixa/média — mesmo padrão de "elemento visível que não devia estar" já corrigido uma vez em `PERMISSOES_SPEC.md` §8.2 (lição: esconder por nível, não só bloquear depois do clique) |

Achado 1 e 2 juntos significam que **a correção do bug não exige desenho
novo de backend** — o `event_games` já é a fonte certa, só falta o
frontend parar de usar o caminho errado e o backend fechar a porta
errada pro público errado (§3).

---

## 3. Fase I — Fechar o escopo de jogos por evento (prioridade — bug de escrita cross-arena)

Decisões propostas (nenhuma fechada ainda — pra validar com o Bruno):

| # | Tópico | Proposta |
|---|---|---|
| I.1 | Fonte de dados do painel de Arena | Aba "Games" do painel de Arena passa a listar via `GET /api/admin/events/{event_id}/games` (jogos vinculados ao evento em contexto, com `ativo`/`ordem` **por vínculo**), não mais `GET /api/admin/games-todos` |
| I.2 | Toggle ativo/inativo | Passa a chamar `PATCH /api/admin/events/{event_id}/games/{game_id}` (já existe, já escopado) em vez de `PATCH /api/admin/games/{game_id}` |
| I.3 | Adicionar jogo já existente ao evento | Tela nova (busca no catálogo global, escopo de leitura — ver I.5), chama `POST /api/admin/events/{event_id}/games/{game_id}` |
| I.4 | Reordenar | Exposto no mesmo endpoint (`ordem`) — drag-and-drop ou setas simples, decisão de UI a fechar na implementação, não afeta modelo |
| I.5 | `PATCH /api/admin/games/{id}` (catálogo global) — quem pode chamar? | Fechar como **só `super`**. Edição de metadado global (nome, `score_max` de catálogo, `plataforma`, `capa_url`, `gameplay_url`) é responsabilidade de quem cuida do catálogo compartilhado — admin de Arena só deveria poder ativar/desativar o jogo **no próprio evento**, nunca editar o registro global. Precisa de teste adversarial explícito (mesmo padrão exigido em `PERMISSOES_SPEC.md` §5.1) confirmando que admin não-super recebe 403 |
| I.6 | Criação de novo jogo (`POST /api/admin/games`) | Já exige `event_id` explícito desde o achado 5.9 do `CATALOGO_JOGOS_SPEC.md` — sem mudança aqui, só confirmar que continua funcionando depois do resto mudar |
| I.7 | Aba "Manutenção" — game selector | Mesmo problema do achado 1 em miniatura: `manut-game-select` (usado por `arquivarJogo()`/`restaurarJogo()`) também lista *todos* os games globais. Como a ação em si já é super-only no backend (achado 5), a correção aqui é só de visibilidade (§4), não de escopo de dados — não around confundir com I.1-I.4 |

**Sem migração de banco** — `event_games` já tem tudo que precisa
(`ativo`, `ordem`, `UNIQUE(event_id, game_id)`). É mudança de frontend +
um ajuste de autorização no backend (I.5).

---

## 4. Fase II — Separação de telas: Console (super) vs. Painel de Arena

| # | Tópico | Proposta |
|---|---|---|
| II.1 | Dois entry points | `admin.html` continua sendo o painel de quem administra uma Arena (admin/moderador de vínculo — feed, wizard, games do evento pós-fix, event config, administradores/convites). `console.html`, novo, é exclusivo de `super` — cross-arena por natureza |
| II.2 | O que migra pro console | Fila de revisão/suspensão de Arena (achado 4), aprovação/mesclagem de jogos pendentes (já super-only no backend, hoje dentro de `tab-games`), catálogo global de jogos pra edição de metadado (consequência de I.5), aba "Exclusões" (já super-only), aba "Manutenção" (achado 5, já super-only) |
| II.3 | O que fica no painel de Arena | Feed de moderação, wizard self-serve, games **do evento** (pós-fix da Fase I), config de identidade visual da própria Arena, aba "Administradores"/convites (já é por vínculo `admin`, não por `super` — `PERMISSOES_SPEC.md` §8.2) |
| II.4 | Código compartilhado | Extrair `admin-common.js` (auth check, `apiFetch`, toast, formatação) reaproveitado pelos dois arquivos — evita duplicar e divergir, mesmo espírito do `temas.js` já compartilhado entre `index.html`/`ranking.html`/`telao.html` |
| II.5 | Navegação entre os dois | `super` logado em `admin.html` de uma Arena específica ganha link pro console (e vice-versa) — decisão de UX a fechar na implementação: super provavelmente ainda precisa entrar no painel de uma Arena específica pra agir "como admin dela" (ex.: revisar feed), então os dois convivem, não se substituem |

---

## 5. Fase III — Fechar gaps funcionais por persona

| # | Tópico | Proposta |
|---|---|---|
| III.1 | Logo real (achado 3) | Reaproveitar `services/storage.py::upload_foto` — decisão a fechar: mesmo bucket `fotos-ranking` com prefixo (`logos/{arena_id}/...`) ou bucket novo dedicado. Logo é asset de branding permanente (nunca devia ser arquivado/expirado como evidência de score) — vale bucket/prefixo próprio pra não herdar semântica errada do bucket de evidência |
| III.2 | Console: fila de revisão + suspensão de Arena (achado 4) | UI simples sobre os endpoints já existentes — sem endpoint novo |
| III.3 | Aba Manutenção — visibilidade (achado 5) | Esconder a aba inteira de quem não é `super`, mesmo padrão já usado pra `tab-btn-wizard`/`tab-btn-administradores`/`tab-btn-exclusoes` |

---

## 6. Cruzamento com `CATALOGO_JOGOS_SPEC.md`

A Fase 2 daquele documento ("painel admin, aba Jogos — revisitado pra
população self-serve") **é, na prática, o mesmo trabalho** das Fases I e
III.2 aqui (fila de aprovação/mesclagem de jogos pendentes, agora
reconhecida como pertencente ao console do super). Ao fechar este
documento, `CATALOGO_JOGOS_SPEC.md` Fase 2 deve ser marcada como
absorvida aqui, não implementada duas vezes.

---

## 7. Riscos identificados

1. **Duplicar lógica entre `admin.html` e `console.html` sem extrair
   compartilhado (II.4) recria o mesmo problema que motivou a separação**
   — dois arquivos divergindo silenciosamente é pior que um arquivo com
   `if (super)`. A extração de `admin-common.js` não é opcional.
2. **I.5 (travar `PATCH /api/admin/games/{id}` pra só super) precisa de
   teste adversarial antes de qualquer coisa ser considerada pronta** —
   mesma exigência que `PERMISSOES_SPEC.md` §5.1 já registrou pra
   concessão de vínculo: checagem de escopo é a única linha de defesa,
   então tem que ser testada com admin de arena tentando editar jogo de
   outra arena, não só caminho feliz.
3. ~~**Migrar o toggle "ativo" pro `event_games` muda o comportamento
   observável de eventos que já usam o toggle antigo.**~~ **Checado em
   produção (2026-08-30) — risco não se confirma.** `event_public.py:116`
   (ranking/telão/play escopados por evento) já usa exclusivamente
   `event_game_repo.listar_por_event` — nunca lê `games.ativo` sozinho.
   `games.ativo` global só alimenta o placar **sem evento**
   (`escopo='global'`, `game.py::listar_ativos`) — uso legítimo,
   intencional, do modelo multi-evento (`SPEC.md` §5.4), não um efeito
   colateral acidental. Existem hoje 3 jogos (variantes de "Moonwalker")
   ativos globalmente sem nenhuma linha em `event_games` — não aparecem
   em ranking de nenhum evento específico hoje, só no placar global; a
   Fase I não muda esse comportamento, só para de mostrá-los na aba
   "Games" do painel de Arena (correto — não pertencem a nenhum evento
   ainda). Se um admin quiser vinculá-los a um evento, usa o fluxo I.3.

---

## 8. Fora de escopo desta rodada

Reordenar jogos por drag-and-drop (fica UI simples de setas na primeira
versão, se decidido); mecanismo de aprovação de logo por super (logo é
liberado direto, sem fila — mesmo risco/tratamento de outros campos de
identidade visual hoje); qualquer redesenho visual/CSS além do necessário
pra separar as duas telas.
