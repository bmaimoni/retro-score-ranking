# Painéis Admin: separação Console (super) vs. Painel de Arena, e correção do escopo de jogos por evento

> Status: **Fase 0 fechada** — query nova validada contra Postgres real
> e validação manual em navegador feita em produção pelo Bruno em
> 2026-09-01 (contexto de Arena + tela inicial + extração mínima de
> `console.html` — ver §0).
> Fases I-III seguem **em especificação — decisões abertas, nenhuma
> fechada ainda**.
> Complementa `PERMISSOES_SPEC.md` (regras de nível/escopo, que não mudam
> aqui) e se sobrepõe parcialmente a `CATALOGO_JOGOS_SPEC.md` Fases 2-4
> (painel "Jogos" revisitado pra escala self-serve) — ver §5. Escrito a
> partir de uma queixa concreta do Bruno sobre a experiência de admin
> hoje, não de uma ideia abstrata de reorganizar telas.

---

## 0. Fase 0 — Contexto de Arena + tela inicial (2026-08-30)

Nasceu de uma segunda queixa concreta do Bruno, depois de fechadas as 3
specs de papel (`MODERADOR_SPEC.md`, `ARENA_ADMIN_SPEC.md`,
`SUPER_SPEC.md`): `admin.html` não mostra pro admin **onde ele está**
(sem logo/identidade visual da própria Arena), não tem tela inicial com
resumo dos próprios events, e mistura configuração de **plataforma
inteira** com configuração de **event/arena específico** na mesma aba,
sem indicar a diferença — risco real de o admin achar que está mudando
algo estreito e na verdade mudar algo global.

Investigando antes de desenhar: isso não é uma queixa nova e sim a peça
que faltou pra Fase II.1 (§4) já fechada neste documento — aquela fase
já escreve "`admin.html` continua sendo o painel de quem administra
**uma** Arena", mas isso nunca foi implementado. Hoje `admin.html` trata
"admin de N Arenas" como lista achatada (`carregarEventos()` em
`frontend/admin.html:2995` busca `/events` de todas as Arenas do admin
de uma vez e renderiza tudo junto, distinguindo só por um `· {arena}`
discreto ao lado do nome — fácil de não notar com 2+ Arenas). A aba
"Event" (`id="tab-config"`, `admin.html:848-975`) empilha, sem
hierarquia visual: identidade/lista de Arenas, lista de events de todas
as Arenas, Avatares (catálogo global), e "Configurações gerais"
(`event_config` — kill-switch de upload, rate limit, texto LGPD,
**plataforma inteira**, não do event/arena atual). Essa última seção é
o achado mais grave: já é `super`-only no backend desde
`MODERADOR_SPEC.md` M.2, mas continua misturada visualmente com
configuração de escopo estreito pra quem é super.

### Decisões (fechadas com o Bruno)

| # | Tópico | Decisão |
|---|---|---|
| F0.1 | Onde documentar | Dobrar neste documento como Fase 0, não abrir spec nova — evita 2 documentos falando da mesma tela e mantém os achados 1-5 (§2) junto da decisão que os antecede |
| F0.2 | Contexto de escopo | **Seletor de "Arena ativa" na topbar, todas as abas herdam.** Troca de Arena vira ação explícita (mesmo espírito do seletor de event que já existe pro Feed, promovido pra nível de Arena inteira); o resto da tela passa a ser sempre relativo à Arena ativa, nunca lista achatada de tudo que o admin tem acesso |
| F0.3 | Tela inicial | Nova aba "Início" (landing, antes de "Feed"), mostrando identidade visual da Arena ativa (logo/cor aplicados na própria topbar do painel, não só no site público) e um resumo dos events dessa Arena: nome, ativo/arquivado, janela de envio (`data_inicio`/`data_fim`), contagem de recordes (`entries` não-arquivadas) por event |
| F0.4 | "Configurações gerais" (plataforma inteira) | **Sair de `admin.html` agora**, não esperar a Fase II inteira — já é `super`-only no backend (M.2), deixar misturada com config de escopo estreito é o próprio bug relatado. Migra pra um `console.html` novo, mínimo |
| F0.5 | Escopo do `console.html` nesta rodada | Além de Configurações gerais: **Avatares** (mesma classe — catálogo global, já `super`-only) e **Manutenção** (limpar/restaurar ranking — já `super`-only, e é o achado 5/§2 item 5 deste documento: aba visível indevidamente pra não-super hoje). Games pendentes/aprovação, fila de revisão de Arena e Exclusões ficam pra Fase II/III completas — não expandir mais que isso agora |
| F0.6 | Código compartilhado | Decisão original era extrair `admin-common.js` com o login-gate inteiro. **Revisado na implementação** (ver nota abaixo) — o login-gate (Google/Magic Link, ~200 linhas testadas em produção) ficou só em `admin.html`; `console.html` reaproveita a mesma sessão (cookie ou `sessionStorage.admin_secret`, mesma origem) sem formulário de login próprio, chamando `/api/admin/me` direto — se falhar ou não for super, manda a pessoa pra `admin.html`. `apiFetch`/`escapar`/`showToast` foram duplicados (poucas linhas, estáveis, baixo risco), não extraídos em módulo — ver risco 4 |
| F0.7 | Definição de "recordes gerados" | `COUNT(entries)` do event com `arquivado = false` — inclui pendentes/ocultas (ainda são um envio real), exclui só o que foi formalmente invalidado por moderação. Decisão reversível, fácil de trocar se o Bruno achar que devia contar diferente depois de ver a tela |

### O que NÃO muda nesta rodada

Escopo de jogos por evento (Fase I — achado 1/2, toggle "ativo" ainda
chama o catálogo global) e a separação completa Console/Painel (Fase II
inteira — fila de revisão de Arena, aprovação de jogos, Exclusões)
continuam em aberto, sem decisão fechada. `console.html` nasce nesta
rodada, mas só com o conteúdo do F0.5 — crescer pra abrigar o resto da
Fase II é trabalho futuro, não incluído aqui.

### Riscos identificados

1. **F0.6 revisado — duplicação de `apiFetch`/`escapar`/`showToast` entre
   `admin.html` e `console.html`.** Aceito conscientemente: são funções
   pequenas e estáveis (não mudaram desde que o projeto existe), e o
   login-gate inteiro (Google OAuth + Magic Link, com popup/redirect,
   ~200 linhas) é frágil demais pra refatorar sem conseguir testar em
   navegador de verdade nesta sessão. Extrair `admin-common.js` de
   verdade (login incluso) fica pra quando a Fase II for implementada
   com espaço pra testar o fluxo de login pós-refatoração.
2. ~~**Query de `resumo` (F0.3) não tem teste contra Postgres real**~~
   **Validada em 2026-08-31** contra o Postgres de produção (Supabase,
   via `DATABASE_URL` de `backend/.env`, só leitura). `EXPLAIN ANALYZE`
   nas 2 Arenas existentes mostra seq scan barato (dataset pequeno hoje,
   sem índice faltando de forma preocupante) e os totais batem com uma
   contagem manual cruzada (`JOIN` + filtro direto, sem `FILTER`/`GROUP
   BY`): Canal3 → evento ativo com 128 recordes, evento arquivado com 0;
   Old School Pinball → evento ativo com 0. Sem mismatch.
3. ~~**Sem teste de navegador pra `admin.html`/`console.html`**~~
   **Validado em 2026-09-01** em produção pelo Bruno: login, identidade
   SUPER no topbar, seletor de Arena trocando logo/nome/resumo, aba
   "Início" com resumo de events, link e acesso a `console.html` como
   super. Automação via Playwright (`tests/smoke/smoke_paineis_admin_fase0.py`,
   escrita nesta sessão) **não rodou** — o sandbox não tem as
   dependências de sistema do Chromium (`libnss3` e ~35 outros pacotes)
   e não há sudo/Docker disponível pra instalá-las; validação ficou
   manual. Nota de honestidade: o caso "`console.html` como não-super"
   foi validado só via proxy (aba anônima, sem sessão nenhuma) — mesmo
   branch de código (`!meInfo || !meInfo.super`) que cobre um admin
   logado mas sem `super`, mas não é literalmente o mesmo teste; não
   existe hoje conta de admin de Arena não-super pra testar o caso
   exato. Risco residual baixo (é o mesmo `if` no código-fonte,
   `frontend/console.html:282`), registrado aqui em vez de escondido.

### Implementação (fechada)

- [x] Backend: `arena_repo.listar_resumo_events_da_arena` +
  `GET /api/admin/arenas/{arena_id}/resumo` (mesmo padrão de escopo do
  `wizard-status` — super ou vínculo na arena). `arena_id` adicionado a
  `listar_events_acessiveis_detalhado` (base de `GET /me`), pra o
  event-selector do Feed também filtrar pela Arena ativa.
- [x] Frontend `admin.html`: seletor de Arena ativa no topbar (herdado
  por Início, Event/Games-config e Feed), aba "Início" nova com
  identidade visual aplicada (logo/cor/tipografia) e resumo de events
  com contagem de recordes, link pro `console.html` pra quem é super.
  Aba "Manutenção" renomeada pra "Telão" (só sobrou o card de telão,
  que nunca foi super-only).
- [x] `console.html` novo: Configurações gerais, Avatares e Manutenção
  — todo o conteúdo já `super`-only no backend, sem endpoint novo.
- [x] Testes: 4 novos (`tests/test_arenas_resumo.py` — resumo com
  contagem, 404, 403 de arena alheia, 200 de arena própria). Suíte
  completa: 677 passed (18 erros de smoke pré-existentes, baseline
  inalterado). `tests/smoke/smoke_paineis_admin_fase0.py` (Playwright,
  7 casos) escrito, mas nunca rodado — ver risco 3.
- [x] Validação manual em navegador — feita em produção em 2026-09-01
  pelo Bruno, ver risco 3.
- [x] Validação da query `resumo` contra Postgres real — feita em
  2026-08-31, ver risco 2.

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
