# Painéis Admin: separação Console (super) vs. Painel de Arena, e correção do escopo de jogos por evento

> Status: **Fase 0 fechada** — query nova validada contra Postgres real
> e validação manual em navegador feita em produção pelo Bruno em
> 2026-09-01 (contexto de Arena + tela inicial + extração mínima de
> `console.html` — ver §0).
> Fase I fechada em 2026-09-01, validada em produção pelo Bruno —
> descoberta: I.5 já estava corrigida antes desta fase (`dce422c`/AA.2),
> escopo real virou "religar frontend nos endpoints certos", não mais
> bug de segurança. Bruno notou elementos de UI que vai querer ajustar
> depois (não especificado ainda). Fase III.1 (upload de logo real),
> III.2 (console: moderação de Arena) e o essencial de Fase II
> (jogos pendentes + catálogo global migrados pro console) implementados
> em 2026-09-01 — todos pendentes de validação manual. III.3, II.1,
> II.3 e II.5 já estavam resolvidos por trabalho de fases anteriores,
> sem terem sido marcados. Só ficou de fora, de propósito: II.2/aba
> Exclusões (baixo risco como está) e II.4/`admin-common.js` (adiada —
> mexe no login-gate, sem como testar em navegador real neste
> ambiente).
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

## 3. Fase I — Fechar o escopo de jogos por evento (2026-09-01)

> **I.5 já estava fechada antes desta fase começar** — descoberto
> investigando o código antes de implementar, não decidido agora.
> `PATCH /api/admin/games/{id}` já é `super`-only no backend desde o
> commit `dce422c` (`_exigir_super_editar_game`,
> `backend/routers/admin.py:439`, ref. `ARENA_ADMIN_SPEC.md` AA.2), e o
> frontend já esconde o toggle de quem não é super
> (`admin.html:1765`). **Consequência não intencional dessa correção**:
> hoje **nenhum admin de Arena (nem super) consegue ativar/desativar
> game no próprio event pela aba Games** — o achado 1 (bug de
> segurança) já não existe, sobrou o achado 2 (funcionalidade quebrada/
> ausente, endpoint certo nunca religado). Fase I fecha isso, não o bug
> de escrita cross-arena (que já não existe).

Decisões (fechadas com o Bruno):

| # | Tópico | Decisão |
|---|---|---|
| I.1 | Fonte de dados do painel de Arena | Aba "Games" do painel de Arena passa a listar via `GET /api/admin/events/{event_id}/games` (jogos vinculados ao evento em contexto, com `ativo`/`ordem` **por vínculo**), não mais `GET /api/admin/games-todos` |
| I.2 | Toggle ativo/inativo | Passa a chamar `PATCH /api/admin/events/{event_id}/games/{game_id}` (já existe, já escopado) em vez de `PATCH /api/admin/games/{game_id}` — volta a ficar visível pra admin comum, não só super (é o vínculo do próprio event, nunca mais o catálogo global) |
| I.3 | Adicionar jogo já existente ao evento | Tela nova (busca no catálogo global, escopo de leitura), chama `POST /api/admin/events/{event_id}/games/{game_id}` |
| I.4 | Reordenar | Exposto no mesmo endpoint (`ordem`) — **setas simples (↑/↓) na v1**, não drag-and-drop (já era o fallback padrão do §8 desta rodada; não é decisão de produto que precise de novo martelo) |
| I.5 | `PATCH /api/admin/games/{id}` (catálogo global) — quem pode chamar? | **Já fechado como só `super`** antes desta fase (ver nota acima) — nada a fazer aqui |
| I.6 | Criação de novo jogo (`POST /api/admin/games`) | Já exige `event_id` explícito desde o achado 5.9 do `CATALOGO_JOGOS_SPEC.md` — sem mudança aqui, só confirmar que continua funcionando depois do resto mudar |
| I.7 | Aba "Manutenção" — game selector | Mesmo problema do achado 1 em miniatura, mas **fora de escopo desta fase** — a ação em si já é super-only no backend (achado 5), a correção é só de visibilidade, fica pra Fase III.3 junto do resto da limpeza de abas mal escondidas |
| I.8 | Escopo de event pra `super` na aba Games | "Quais games estão ativos no event X" não é agregável entre events como o Feed é — mesmo super precisa escolher um event específico pra usar a aba Games. **Seletor de event só dentro da aba Games**, não promovido pro topbar/outras abas — Feed continua sem seletor pra super (agregado, como já é desde F0.2) |

**Sem migração de banco** — `event_games` já tem tudo que precisa
(`ativo`, `ordem`, `UNIQUE(event_id, game_id)`). Precisou de **um**
ajuste pequeno de backend, achado na implementação (não previsto nas
decisões acima):

> `event_game_repo.listar_por_event` (o "endpoint certo" do achado 2)
> filtra `WHERE ej.ativo = true` de propósito — é a versão pública,
> usada por ranking/telão, que nunca deve mostrar jogo desligado. Mas a
> rota admin (`GET /api/admin/events/{id}/games`) reusava a mesma
> função — então assim que um admin desativasse um game pela aba
> Games, ele **sumiria da lista pra sempre**, sem jeito de reativar
> pela própria tela. Corrigido com uma função nova só pro admin,
> `listar_por_event_admin` (retorna ativo e inativo, mais
> `jogo_ativo_global`/`pendente_aprovacao` do catálogo pra contexto) —
> a versão pública não mudou.

### Implementação (fechada — pendente só de validação manual)

- [x] Backend: `event_game_repo.listar_por_event_admin` (nova, ver nota
  acima) + `GET /api/admin/events/{id}/games` passa a usá-la. 2 testes
  novos em `test_events.py` (patch do mock atualizado pro nome novo +
  regressão explícita do "vínculo inativo não some da lista"). Suíte
  completa: 668 passed (10 erros pré-existentes de conexão real com
  Postgres, baseline confirmado igual antes/depois desta mudança via
  `git stash`).
- [x] Frontend `admin.html`, aba "Games" reescrita:
  - I.1/I.2: lista e toggle via `event_games`, escopados por
    `eventoAtual` (herdado do Feed pra admin/moderador; seletor
    dedicado só nesta aba pra `super`, I.8).
  - I.3: busca no catálogo (`games-todos`, cacheado em
    `catalogoGlobal`) + botão adicionar ao event.
  - I.4: reordenar com setas ↑/↓, renumera a lista inteira em sequência
    a cada troca (evita ficar preso em `ordem` duplicado quando vários
    games nascem com `ordem=0`).
  - I.6: `criar-game-btn` agora envia `event_id: eventoAtual` — antes
    criava o game sem vínculo nenhum (gap não documentado, achado
    nesta implementação: a versão anterior nunca mandava `event_id`,
    então nenhum game criado pelo painel aparecia em nenhum event).
  - Visibilidade: toggle/reordenar/adicionar só aparecem pra quem é
    `admin` (ou super) **na Arena ativa** — moderador continua lendo a
    lista (backend já libera), mas não vê os controles de edição
    (mesmo padrão de `docs/PERMISSOES_SPEC.md` §7 item 5, "esconder
    por nível, não só bloquear depois do clique").
  - `feed-filtro-game` (dropdown de filtro do Feed) desacoplado da
    lista de games do event — antes vinha de `renderJogos` (que agora
    é só o event ativo), teria regredido pra `super` (perderia a opção
    de filtrar por qualquer game da plataforma). Agora vem de
    `catalogoGlobal`, carregado uma vez, independente do event em
    contexto.
- [x] Validação manual em navegador — feita pelo Bruno em produção em
  2026-09-01, "funcionando". Ele notou elementos de UI que vai querer
  mudar (não bloqueante, não especificado ainda — registrar quando
  ele fechar o que exatamente quer mudar).
- [ ] Smoke test Playwright automatizado — **decisão consciente de não
  escrever nesta rodada**: ao contrário da Fase 0 (só leitura/
  navegação), validar I.2/I.3/I.4 de ponta a ponta significa mutar
  dados reais em produção (ativar/desativar e adicionar game a um
  event de verdade) — sem ambiente de teste isolado (ver
  `docs/SPEC.md` §9, sem staging), automatizar isso contra produção é
  risco desproporcional ao ganho. Validação fica manual, feita com
  cuidado (evento de baixo risco, ex: Old School Pinball, que hoje tem
  0 recordes) — ver checklist passado ao Bruno.

### Riscos identificados

1. **Sem teste de navegador** — mesma lacuna da Fase 0, mas agora com
   ações que **mutam dado real** (toggle ativo, adicionar game,
   reordenar), não só leitura. Peço validação manual cuidadosa antes
   de fechar esta fase — ver checklist.
2. **Reordenar renumera a lista inteira a cada clique** (N requests
   PATCH em paralelo, N = quantidade de games do event) — decisão
   deliberada pra nunca ficar preso em `ordem` duplicado, mas significa
   mais chamadas de rede que um swap de 2 valores. Sem impacto real
   hoje (poucos games por event), reavaliar se algum event crescer pra
   dezenas de games.

---

## 4. Fase II — Separação de telas: Console (super) vs. Painel de Arena

| # | Tópico | Status |
|---|---|---|
| II.1 | Dois entry points | ~~Proposta~~ **Já é a realidade** desde a Fase 0: `admin.html` é o painel de quem administra uma Arena, `console.html` (novo na Fase 0) é exclusivo de `super` |
| II.2 | O que migra pro console | Fila de revisão/suspensão de Arena → **feito (III.2, 2026-09-01)**. Aprovação/mesclagem de jogos pendentes + catálogo global pra edição de metadado → **feito (2026-09-01, ver §implementação abaixo)**. Aba "Exclusões" → **ainda não migrada**, mas já é super-only dentro do `admin.html` (`tab-btn-exclusoes` escondido de quem não é super desde antes desta spec) — baixo risco ficar assim por ora, não fazia parte do escopo combinado com o Bruno nesta rodada. Aba "Manutenção" → já migrada desde a Fase 0 |
| II.3 | O que fica no painel de Arena | ~~Proposta~~ **Já é a realidade**: Feed, wizard, games do event (Fase I), config de identidade visual, Administradores/convites — tudo já em `admin.html` |
| II.4 | Código compartilhado | **Ainda não feita, adiada de propósito** — extrair `admin-common.js` mexe no login-gate (Google OAuth + Magic Link, ~200 linhas testadas em produção), e este ambiente de sandbox não tem como testar login em navegador de verdade (sem sudo/Docker pro Playwright — ver `[[project_sandbox_env_constraints]]`). Fica pra quando houver espaço de testar o fluxo pós-refatoração |
| II.5 | Navegação entre os dois | ~~Proposta~~ **Já existe nos dois sentidos**: `console.html` tem "← Painel de Arena" no topbar, `admin.html` tem "⚙ Ir para o Console" na aba Event (pra quem é super) |

### Implementação II.2 — jogos pendentes + catálogo global (2026-09-01)

- [x] `admin.html`: removida a seção "Games aguardando aprovação"
  (HTML + JS + CSS não mais usado) e o hook de carregar no clique da
  aba Games. **Achado na remoção**: o select de "mesclar com" dessa
  seção montava as opções a partir de `jogosCache` — que desde a Fase
  I passou a ser só os games do event ativo (não mais o catálogo
  inteiro). A seção já estava com escopo errado havia dias sem
  ninguém notar (super só via pra mesclar os games do event que
  estivesse olhando por último). Corrigido na migração: a versão nova
  em `console.html` monta essas opções a partir do catálogo completo
  (`games-todos`), sempre.
- [x] `console.html`, aba "Catálogo" nova: seção de pendentes migrada
  (mesmos 3 endpoints já `super`-only —
  `GET /games/pendentes`, `PATCH /{id}/aprovar`, `POST /{id}/mesclar`
  — nenhum endpoint novo) + seção nova de edição de metadado do
  catálogo global (nome/slug não editáveis por design do backend,
  plataforma/ano/score_max/capa/gameplay/ativo sim — via
  `PATCH /api/admin/games/{id}`, já travado pra só `super` desde AA.2).
  Sem endpoint novo nesta parte — só UI que nunca tinha existido.
- Sem testes de backend novos (nenhuma rota nova, nenhuma mudança de
  autorização) — só frontend. Suíte completa: 687 passed, mesmo
  baseline.
- [ ] Validação manual em navegador — pendente.

---

## 5. Fase III — Fechar gaps funcionais por persona

| # | Tópico | Decisão/Status |
|---|---|---|
| III.1 | Logo real (achado 3) | **Fechada e implementada em 2026-09-01.** Decisão do bucket: **mesmo bucket `fotos-ranking`, com prefixo `logos/{arena_id}/`** — não bucket novo. Motivo prático que resolveu o "a fechar": criar bucket novo no Supabase Storage é passo manual fora do código (dashboard ou Management API, que usa credencial diferente da já disponível), enquanto o prefixo resolve a mesma preocupação de semântica (branding permanente vs. evidência de moderação) sem dependência externa nem passo manual — ambos os arquivos já são "nunca deletados" de qualquer forma. Ver §implementação abaixo |
| III.2 | Console: fila de revisão + suspensão de Arena (achado 4) | **Fechada e implementada em 2026-09-01.** Nova aba "Arenas" em `console.html`. Achado na implementação: os endpoints citados no achado 4 (`aprovar`/`suspender`) **nunca tinham teste nenhum** desde que existem (`ARENA_SPEC.md` B.4/C.1) — cobertos agora. Achado mais sério: **não existia jeito de reverter uma suspensão** — sem `GET` listando arenas suspensas nem `PATCH` de reativar, suspender pela UI seria ação só de ida (reverter exigiria mexer direto no banco). Fechado com o Bruno: adicionar `GET /suspensas` + `PATCH /{id}/reativar` (reusam `atualizar_status`, já existia) fazia parte do escopo, não ficou de fora |
| III.3 | Aba Manutenção — visibilidade (achado 5) | ~~Ainda proposta~~ **Já resolvida pela Fase 0** (2026-08-30, não documentado na hora): a aba virou "Telão" (só o card que nunca foi super-only) e as ações de manutenção de verdade saíram pra `console.html` (F0.4/F0.5), que já é super-only por inteiro. Nada a fazer aqui |

### Implementação III.1 (fechada — pendente de validação manual)

- [x] Backend: `services/storage.py` ganhou `upload_logo(foto, arena_id)`
  (reusa a lógica de `upload_foto` via helper `_fazer_upload` novo, só
  muda o prefixo do path). Endpoint novo
  `POST /api/admin/arenas/{arena_id}/logo` (`routers/arenas_admin.py`)
  — mesma régua de autorização do `PATCH /{arena_id}` (admin da própria
  arena ou super), mesma validação de upload do `event_public.py`
  (magic bytes, 5MB, JPEG/PNG). Retorna só `{logo_url}` — o frontend
  salva no registro da arena chamando o `PATCH` já existente, sem
  endpoint novo pra isso. 7 testes novos (`test_storage.py`,
  `test_arenas_admin.py`: ok, 404, 403 de arena alheia, 403 moderador,
  >5MB, PDF disfarçado de jpg). Suíte completa: 675 passed (mesmo
  baseline de 10 erros pré-existentes).
- [x] Frontend: os **dois** pontos que setam `logo_url` ganharam upload
  de arquivo (campo texto de URL continua existindo, upload só
  preenche ele — sem duplicar o fluxo de salvar):
  - Form "criar/editar arena" (`admin.html`, aba Event) — upload só
    funciona em modo edição (precisa de `arena_id`, que não existe
    ainda ao criar); criar continua exigindo URL colada ou salvar
    primeiro e editar depois.
  - Wizard de personalização pós-ativação (`ARENA_SPEC.md` Fase E) —
    upload sempre disponível, arena já existe nesse ponto do fluxo.
- [ ] Validação manual em navegador — pendente (upload de arquivo real
  contra o Supabase Storage de produção, não simulável sem browser).

### Implementação III.2 (fechada — pendente de validação manual)

- [x] Backend: `arena_repo.listar_suspensas` nova (espelha
  `listar_pendentes`, filtra `status='suspended'`).
  `GET /api/admin/arenas/suspensas` e `PATCH /{arena_id}/reativar`
  novos (reusam `atualizar_status`, `'suspended'`→`'published'`, mesmo
  espírito de `aprovar_arena` — não distingue se a arena suspensa
  tinha vindo de `draft` ou de `published`, sempre publica direto ao
  reativar). 12 testes novos cobrindo os 5 endpoints do cluster
  inteiro (`pendentes`/`aprovar`/`suspender`/`suspensas`/`reativar`) —
  os 3 que já existiam (`pendentes`/`aprovar`/`suspender`) não tinham
  teste nenhum antes. Suíte completa: 687 passed (mesmo baseline de 10
  erros pré-existentes).
- [x] Frontend: aba "Arenas" nova em `console.html` — lista de fila de
  revisão (aprovar/rejeitar) e lista de arenas suspensas (reativar).
  "Rejeitar" na fila chama o mesmo endpoint de `suspender` (mesmo
  estado final `suspended`, não existe estado "rejeitada" à parte —
  ver docstring de `suspender_arena` no backend).
- [ ] Validação manual em navegador — pendente. Hoje em produção não
  há nenhuma arena em `draft` nem `suspended` (só as 2 já publicadas),
  então validar de ponta a ponta exige criar uma arena de teste que
  caia em revisão (nome quase-igual a uma existente, ou 2ª+ criação
  pela mesma conta em 24h — `ARENA_SPEC.md` B.4) — ver nota pro Bruno.

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
2. ~~**I.5 (travar `PATCH /api/admin/games/{id}` pra só super) precisa
   de teste adversarial**~~ **Já coberto** — confirmado ao revisitar o
   doc pra Fase I (2026-09-01): `test_atualizar_game_admin_de_arena_retorna_403`
   e `test_atualizar_game_moderador_retorna_403` (`tests/test_admin.py`)
   já existem desde o commit `dce422c`/AA.2, cobrindo exatamente esse
   caso adversarial.
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
