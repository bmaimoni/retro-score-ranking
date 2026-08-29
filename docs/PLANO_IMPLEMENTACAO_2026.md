# Plano de Implementação — Backlog 2026

> Todas as decisões de arquitetura estão fechadas (ver `docs/BACKLOG_2026.md`
> e os 5 documentos referenciados nele). Este documento organiza **a ordem
> de execução** — por dependência real entre as peças, não pela ordem em
> que discutimos. Nenhuma fase começa antes da anterior estar validada em
> produção, seguindo o mesmo processo já usado no projeto inteiro: migração
> testada localmente → aplicada → backend → testes → frontend → validação.

Próxima migração livre: **`029`**.

**Fase 1 concluída** (migração 019, ver `docs/PERMISSOES_SPEC.md` §7).
**Fase 2 concluída** (migrações 020-022, ver `docs/NICKNAME_SPEC.md` e
`docs/EXCLUSAO_CONTA_SPEC.md`). **Fase 3 concluída** (migração 023, ver
`docs/SEGUIR_SPEC.md`). **Fase 4 concluída** (migrações 024-025, ver
`docs/RANKINGS_CONFIGURAVEIS_SPEC.md`). **Fase 5 concluída** (sem
migração — extensão pura de `WHERE`, nenhuma mudança de schema, ver
`docs/BACKLOG_2026.md` §4). **Fase 6 concluída** (sem migração —
`frontend`/`marcas_publico` novo endpoint público, sem schema novo, ver
`docs/BACKLOG_2026.md` §2/§3.4). Todas aplicadas em produção, backend e
frontend prontos. Backlog do plano original está completo — itens
menores pendentes seguem em `docs/BACKLOG_2026.md` §5, sem ordem de
execução fechada.

**Fases 7-10 sequenciadas em 2026-08-27**, a partir de `docs/ARENA_SPEC.md`
(especificação completa, Fases A-H fechadas) — pivô estratégico
casual-first: o container `marca` vira **Arena**, nasce self-serve (sem
`super` como gatekeeper único), com efeito de rede via identidade de
jogador cruzando Arenas, wizard de onboarding e convite assíncrono de
coadministração. Nenhuma delas começou a ser implementada ainda.

---

## Por que esta ordem, e não outra

`PERMISSOES_SPEC.md` é a única peça que **bloqueia** praticamente tudo o
resto: `eventos.marca_id NOT NULL` é pré-requisito de `RANKINGS_CONFIGURAVEIS_SPEC.md`
(que adiciona uma coluna em `eventos` presumindo marca sempre presente), e
o modelo de `nivel` (admin/moderador) é pré-requisito de qualquer
autorização nova no Admin. Por isso vai primeiro, mesmo sendo a decisão
mais antiga desta rodada de análise.

As demais fases foram agrupadas por **dependência**, não por seção do
backlog original — por exemplo, "Perfil" e "Tela Inicial" do documento de
compilação viraram fases diferentes, porque parte de Tela Inicial (prefill
de nick/avatar) depende de decisões de Perfil, mas scroll infinito não
depende de nada.

---

## Fase 1 — Permissões e Marca Obrigatória ✅ concluída

**Spec**: `docs/PERMISSOES_SPEC.md`
**Bloqueia**: Fases 2, 4, 6 (parcialmente)

- **Pré-requisito, antes de qualquer migração**: consultar produção,
  confirmar `SELECT COUNT(*) FROM eventos WHERE marca_id IS NULL` = 0. Se
  houver órfão, vincular manualmente antes de prosseguir — a migração
  quebra em produção se isso não for feito antes.
- Migração: `admin_vinculos` (remove `escopo='evento'`, adiciona `nivel`),
  `eventos.marca_id NOT NULL`, `marcas.dono_user_id`,
  `admin_vinculos_auditoria` — RLS + policy desde o início.
- Backend: reescrever `middleware/auth.py` e `repositories/admin_vinculo.py`
  pra resolver nível por marca; endpoint de transferência de titularidade
  dedicado; corrigir `POST /api/admin/marcas` pra exigir `super`; toda
  concessão/revogação grava em `admin_vinculos_auditoria`; **corrigir
  `routers/admin.py:criar_jogo`** pra exigir nível `admin` (bloquear
  `moderador` — achado registrado em `BACKLOG_2026.md` §4).
- Testes: cobertura adversarial de isolamento cross-marca em cada endpoint
  escopado — categoria obrigatória, não opcional, dado o risco de negócio.
- Frontend: `admin.html` ganha seletor de nível na UI de vínculos;
  condicional por nível (esconder ações que o nível atual não permite, não
  só bloquear depois do clique).

---

## Fase 2 — Identidade do Jogador (Perfil, Nickname, Exclusão, Avatar) ✅ concluída

**Specs**: `docs/NICKNAME_SPEC.md`, `docs/EXCLUSAO_CONTA_SPEC.md`,
mais os itens de avatar/campos de perfil documentados direto em
`docs/BACKLOG_2026.md` §1.
**Depende de**: Fase 1 (exclusão de conta usa a trava de titularidade)
**Bloqueia**: Fase 6 (prefill de nick/avatar na tela inicial)

- [x] Migração (020-022, aplicadas em produção): `users` ganha
  `nome_completo`, `data_nascimento`, `cidade`, `estado`, `telefone`,
  `avatar_id`, `exclusao_solicitada_em`, `status` ganha `'excluido'`;
  `nick_claims` ganha `ativo` (índice único parcial) e `nick` (versão de
  exibição — gap achado na implementação, migration 021); `avatares`
  (nova, curada por `super`); `entradas.pendente_motivo`;
  `nick_troca_forcada_auditoria` (nova).
- [x] Backend: endpoints de perfil (ver/editar, `GET /api/perfil/pontuacoes`
  com jogo/evento/marca); troca de nick com cooldown de 30 dias + liberação
  imediata + claim retroativo (`POST /api/perfil/nick`); moderador força
  troca sem cooldown com auditoria (`POST /api/admin/usuarios/{id}/trocar-nick`);
  fila de revisão por identificação ambígua (reaproveita a fila de
  pendentes existente, arquivamento automático depois de 30 dias via
  checagem preguiçosa, sem cron); exclusão de conta (bloqueio se
  `dono_user_id`, janela de 30 dias, processamento manual por `super` via
  `GET/POST /api/admin/exclusoes-pendentes`, anonimização cobrindo `users`
  + `identities.email` + `magic_link_tokens.email`); desativar pontuações
  em massa; CRUD de avatares (`super`) + seleção (usuário).
- [x] Frontend: `perfil.html` nova (ver/editar dados, trocar nick, escolher
  avatar, detalhamento de pontuações próprias com link pro jogo, desativar
  pontuações, solicitar/cancelar exclusão, logout); `index.html` ganha link
  "Meu perfil"; `admin.html` ganha CRUD de avatares, histórico de nicks +
  força-troca no feed, e aba de exclusões pendentes.

---

## Fase 3 — Seguir e Feed de Atividade ✅ concluída

**Spec**: `docs/SEGUIR_SPEC.md`
**Depende de**: nada crítico (só precisa que a tela de perfil exista —
pode ser feita junto com a Fase 2, na prática, mas é logicamente
independente)

- [x] Migração 023: `seguidores` (nova).
- [x] Backend: seguir/deixar de seguir (soft, `ativo=false` — achado na
  implementação, não estava no §4 original mas segue a convenção do
  projeto); `GET /api/perfil/atividade` compila a comparação de melhor
  score. Achado na implementação: `users.ultimo_login_em` não podia mais
  ser atualizado no momento do login em si (login via Google é redirect,
  sem como devolver o feed computado nessa resposta) — a atualização foi
  deslocada pra dentro do próprio `GET /api/perfil/atividade`, que lê o
  valor anterior, compila, só então avança. `listar_ranking`/
  `listar_ranking_por_evento` (públicas) passaram a expor `user_id`,
  pré-requisito pro botão de seguir existir.
- [x] Frontend: `perfil.html` ganha card "Seguindo" (abas Sigo/Me seguem);
  `ranking.html` ganha botão "+ seguir" por entrada identificada (único
  jeito de descobrir quem seguir, sem diretório de jogadores);
  `index.html` mostra a mensagem de superação como toast ao confirmar
  sessão.

---

## Fase 4 — Rankings Configuráveis e Metadado de Jogo ✅ concluída

**Spec**: `docs/RANKINGS_CONFIGURAVEIS_SPEC.md`, mais itens 3.1/3.2/3.3/3.6
documentados em `docs/BACKLOG_2026.md` §3.
**Depende de**: Fase 1 (`eventos.marca_id NOT NULL` é pré-requisito direto)

- [x] Migração 024: `eventos.modo_ranking`, `marcas_parcerias` (nova),
  `marcas.itens_por_pagina`, `jogos` ganha `plataforma`/`ano_lancamento`/
  `capa_url`/`gameplay_url` (todos opcionais). Migração 025 (achado na
  implementação): `admin_vinculos_auditoria.user_alvo_id` passa a
  aceitar `NULL` — parceria acionada via bootstrap (`Bearer
  <ADMIN_SECRET>`) não tem `user_id` de sessão pra gravar ali, e é a
  primeira ação auditada onde o "alvo" é o próprio ator, não um usuário
  diferente (mesma categoria de gap já corrigida uma vez na migration 022).
- [x] Backend: `services/ranking.py` resolve os 5 modos (zerado/último
  evento/marca/marca+parceiras/geral), calculado ao vivo via
  `evento_ids` resolvidos por modo, sem dado espelhado;
  `repositories/marca_parceria.py` + endpoints em `marcas_admin.py`
  cobrem liberar/aceitar/revogar (liberação mútua automática ao
  aceitar, tudo-ou-nada, sem granularidade por evento), tudo auditado
  em `admin_vinculos_auditoria`; jogos ganham metadado opcional; marcas
  ganham `itens_por_pagina`. Achado na implementação: o QR de
  `ranking.html` (item 3.3) não podia simplesmente reusar o slug da URL
  em ranking agregado — se a janela de envio do evento sendo
  visualizado já tivesse fechado, o QR apontaria pra um link de envio
  morto mesmo com a marca tendo outro evento ativo. Endpoint novo
  `GET /api/e/{slug}/evento-envio-atual` resolve isso: em modo
  `zerado` devolve o próprio slug; nos modos agregados, o evento
  mais recente/ativo (janela aberta tem prioridade) da marca dona da
  página, via `evento_repo.buscar_evento_envio_atual_da_marca`.
- [x] Frontend: `ranking.html` mostra metadado de jogo; QR real
  (reaproveita `gerarQR` de `telao.html`, resolve o evento de destino
  via `/evento-envio-atual` antes de montar o link); "meu score"
  (`?destaque=`) navega e destaca a melhor entrada da pessoa; `admin.html`
  ganha seletor de `modo_ranking` na criação de evento + `<select>`
  inline por evento pra trocar depois, config de `itens_por_pagina` por
  marca, e painel de parcerias por marca (liberar/aceitar/revogar,
  carregado sob demanda). Todos os controles de gestão respeitam
  "qualquer admin da marca, moderador nunca" (decisão #3 da spec).

---

## Fase 5 — Admin: Filtros de Feed ✅ concluída

**Spec**: itens 4.1/4.3/4.4 documentados em `docs/BACKLOG_2026.md` §4.
**Depende de**: Fase 1 (escopo de evento por nível) e Fase 2 (critério
"sem identificação" já definido em `NICKNAME_SPEC.md`)

- [x] Backend: `GET /api/admin/feed` ganha filtros combináveis — `status`
  (visiveis/ocultos/pendentes/todos — o pill de visibilidade que já
  existia na aba, agora resolvido no banco em vez de no cliente),
  `data_de`/`data_ate`, `jogo_id`, `sem_foto`, `sem_identificacao`
  (`user_id IS NULL AND nome IS NULL`, mesmo critério da decisão #7 do
  `NICKNAME_SPEC.md`) — mais `busca` (item 4.4) via `ILIKE` sobre
  nick/jogo/evento, sem full-text search. `evento_id` (escopo por
  nível) já existia antes da Fase 5, não é filtro novo.
  `repositories/entrada.py` ganhou `_filtros_feed_sql`, helper
  compartilhado entre `listar_feed_admin`/`contar_feed_admin` — as duas
  precisam aplicar exatamente os mesmos filtros, senão `X-Total-Count`
  diverge da página retornada.
- [x] Frontend: `admin.html` ganha UI de filtros na aba Feed (busca com
  debounce, seletor de jogo, intervalo de datas, checkboxes sem
  foto/sem identificação, botão limpar filtros) e paginação real
  (Anterior/Próxima + `X-Total-Count`), substituindo o fetch de
  `limit=100` + filtro no cliente que existia antes. Achado na
  implementação: o contador do pill "Pendentes" e o badge de "recentes"
  da aba antes vinham só do topo de 100 itens buscado (aproximação, não
  o total real) — viraram consultas leves e independentes da
  página/filtro em exibição, sempre refletindo o estado global de
  verdade.

---

## Fase 6 — Tela Inicial e Navegação ✅ concluída

**Spec**: itens 2.1-2.4 e 3.4, documentados em `docs/BACKLOG_2026.md` §2/§3.
**Depende de**: Fase 2 (prefill de nick/avatar), beneficia-se da Fase 1
(critério de marca "válida" já resolvido)
**Sem dependência de**: nada impede fazer isso mais cedo, exceto o prefill

- [x] Backend: único endpoint novo da fase — `GET /api/marcas/com-evento-ativo`
  (`routers/marcas_publico.py`), pra `index.html` descobrir marca/evento
  quando não há `?evento=` na URL. Reaproveita `evento_repo.buscar_
  evento_envio_atual_da_marca` (já existia desde a Fase 4, mesmo critério
  do QR em ranking agregado) — sem duplicar a lógica de "qual evento
  oferecer" em dois lugares.
- [x] `index.html`: fallback hardcoded (`|| 'canal3expo'`) removido sem
  rede de segurança, confirmado sem QR/material físico dependendo dele
  (item 2.1). Sem `?evento=`: marca única pula direto pro fluxo dela;
  0 marcas mostra estado vazio; 2+ mostra seletor (reaproveita a classe
  `.jogo-card` da lista de jogos — zero CSS novo pro seletor). Copy
  "Salve suas pontuações!" no lugar de "Entrar para proteger seu nick"
  (item 2.2). Logado: mostra nick ativo do perfil + avatar (via
  `GET /api/perfil` + `GET /api/avatares`, mesmo padrão de resolução de
  `perfil.html`) e pré-preenche o campo de apelido — só preenche, nunca
  trava o campo (decisão #2 do `NICKNAME_SPEC.md`, item 2.3). Scroll
  infinito (item 2.4): lista inteira já em memória como sempre, lotes de
  20 cards renderizados via `IntersectionObserver` — busca continua
  filtrando sobre a lista completa, não sobre o que já foi renderizado.
  Achado na implementação: sem isso, escolher uma marca no seletor
  deixava o título da página preso em "ESCOLHA O LOCAL" — corrigido
  salvando/restaurando o título original em vez de um valor fixo (o
  título pode já vir customizado de `carregarConfig()`).
- [x] `nav.js` (novo, módulo compartilhado): componente de navegação
  (hamburguer) inserido em `index.html`, `ranking.html` e `perfil.html`
  — **não** em `admin.html` (fica com abas, modelo autenticado
  condicional por nível) nem `telao.html` (uso passivo, sem navegação
  por toque). `ranking.html` preserva o evento atual no link de volta
  pro Início quando há um.

---

## Fase 7 — Rename retroativo de identificadores pra inglês ✅ fechada

**Spec**: `docs/ARENA_SPEC.md` §5/§8 (decisão cross-cutting — escopo
limitado a identificadores de código; prosa dos docs continua em
português)
**Bloqueava**: Fases 8-10 — desbloqueadas

- [x] Migração 026 (`backend/migrations/026_rename_ingles.sql`): rename
  mecânico de tabelas/colunas via `ALTER TABLE ... RENAME` (sem
  `DROP`/`DELETE`, reversível, nenhuma perda de dado) — `marcas`→`arenas`,
  `admin_vinculos`→`memberships`, `admin_vinculos_auditoria`→
  `membership_audit_log`, `entradas`→`entries`, `eventos`→`events`,
  `jogos`→`games`, `marcas_parcerias`→`arena_partnerships`,
  `evento_jogos`→`event_games`; colunas `dono_user_id`→`owner_user_id`,
  `nivel`→`role`, `escopo`→`scope` (mais as FKs correspondentes). Rodada
  com sucesso em produção via Supabase SQL Editor (sem backup prévio —
  decisão explícita, volume de dado irrisório, produto ainda em fase de
  teste).
- [x] RLS/policy: confirmado que `ALTER TABLE ... RENAME TO` no Postgres
  carrega a policy junto automaticamente (ligada por OID, não por nome)
  — nenhuma policy precisou ser recriada.
- [x] Backend: routers/repositórios/rotas renomeados
  (`marcas_admin.py`→`arenas_admin.py`, `admin_vinculos.py`→
  `memberships.py`, etc.), todo código que referenciava os nomes antigos
  atualizado.
- [x] Frontend: `admin.html` e demais telas atualizadas pras rotas novas.
  Parâmetros de URL externos (`?evento=`/`?jogo=`, usados em QR
  code/link já distribuído) preservados de propósito — decisão de
  escopo pra manter zero mudança de comportamento pra quem já tem link
  impresso.
- [x] Testes: suíte inteira ajustada — 568 passed, 10 failed (falhas
  pré-existentes por falta de Postgres real em sandbox, mesma categoria
  já documentada em `SPEC.md` §9, validado manualmente como não-regressão).
- [x] Deploy: migração rodada em produção, código commitado (`5cff69f`,
  `0454cc2`) e push feito — Railway/Vercel redeployam automaticamente a
  partir do push no `main`, aceitando janela curta de indisponibilidade
  entre os dois passos (decisão registrada nesta mesma rodada).
- [x] **Hotfix pós-deploy** (migração 027, `a96fe91`): auditoria
  sistemática (toda referência a nome de tabela no código comparada
  contra o schema real de produção) achou 2 gaps que a 026 deixou
  passar — `membership_audit_log.nivel` nunca virou `role` (quebrava
  todo `INSERT` de auditoria de vínculo) e `evento_config` nunca foi
  renomeada pra `event_config` (quebrava config da tela de upload).
  Ambos corrigidos e validados em produção antes de seguir pra Fase 8.
- [x] **G.1 resolvido**: as 2 Arenas legadas (Canal3, Old School
  Pinball) tinham `owner_user_id` nulo — atribuídas a
  `bmaimoni@gmail.com` como titular temporário (repassar aos admins
  corretos depois, pelo próprio sistema, quando a Fase 10/convite
  existir), com vínculo `admin` + auditoria gravados pelos
  repositórios reais do app, não SQL direto.

---

## Fase 8 — Fundação Arena: admissão, dados e cadastro self-serve ✅ fechada

**Spec**: `docs/ARENA_SPEC.md` Fases B, C, D e G
**Depende de**: Fase 7

- [x] **Pré-requisito resolvido antes da Fase 8 começar**: `owner_user_id`
  nulo nas 2 Arenas legadas (Canal3, Old School Pinball) — atribuído a
  `bmaimoni@gmail.com` como titular temporário (ver nota na Fase 7).
- [x] Migração 028 (`backend/migrations/028_arena_admissao_selfserve.sql`,
  `ad6eb2d`): `arenas.status` (draft/published/suspended, default
  published — C.1/G.1), `arenas.plan` (default free — C.2/G.1),
  `events.visibility` (open/private, default private — D.7). Backfill
  explícito pras linhas legadas (2 Arenas `published`, 2 events `open`)
  pra não sumirem do diretório de descoberta por causa do default novo
  — validado em produção após rodar.
- [x] Backend: `require_super_or_authenticated_user` em
  `middleware/auth.py` (resolve o ovo-e-galinha de `require_admin` —
  usuário sem `membership` nenhum agora consegue criar sua primeira
  Arena) usada só no endpoint de criar Arena. Endpoint único,
  comportamento condicional por quem chama (G.3): `super` inalterado;
  usuário comum passa por rate limit 3/dia (B.3/G.4), colisão de nome/
  slug exata ou substring (B.2), heurística de risco via distância de
  edição (Levenshtein) ≤2 OU 2ª+ Arena em 24h → nasce `draft` (B.4);
  criador vira admin+titular automaticamente. `services/arena_admissao.py`
  novo concentra a lógica pura (normalização, admissão, sanitização de
  `logo_url` contra XSS). Fila de revisão do `super`: `GET /pendentes`,
  `PATCH /aprovar`, `PATCH /suspender` (mesmo estado final pra rejeitar
  fila e pra suspender Arena já pública — justificado no código).
- [x] Testes: `test_arena_admissao_service.py` (12 casos, lógica pura) +
  `test_arenas_admin_selfserve.py` (10 casos, fluxo HTTP completo) — 590
  passed, 10 failed (baseline conhecido, sem banco real).
- [x] Frontend: `index.html` virou home institucional (CTA "criar sua
  Arena", diretório `GET /api/arenas/eventos-abertos` com estado vazio
  tratado — D.1/D.7); `play.html` novo, sem fallback, bloqueia com
  mensagem clara quando falta `?evento=` explícito.
- [x] **Achado fora do escopo original, corrigido na mesma rodada**:
  `ranking.html`/`telao.html` geravam QR code/link de "participar"
  apontando pra `index.html?evento=X` — que virou home institucional e
  ignora esse parâmetro. Sem o fix, QR físico em telão real mandaria
  pra página errada. Corrigido pra `play.html?evento=X` nos dois.
- [x] Deploy: migração rodada em produção, código commitado (`ad6eb2d`)
  e push feito.

**Pendências sinalizadas, não bloqueantes**: login (Google/Magic Link)
não preserva página de origem — quem loga a partir de `play.html` volta
pra home, não pro evento (gap pré-existente ao trabalho desta fase,
ficou mais visível agora); `require_authenticated_user` (dependency mais
fraca, cogitada no planejamento) ficou sem uso — código morto pequeno,
limpar numa rodada futura.

---

## Fase 9 — Wizard de configuração pós-ativação ✅ fechada

**Spec**: `docs/ARENA_SPEC.md` Fase E, fundida com a Fase 1 do
`docs/CATALOGO_JOGOS_SPEC.md` (escolha/cadastro de jogo dentro do
mesmo Passo 1 — as duas são a mesma tela na prática)
**Depende de**: Fase 8

- [x] Migração 029 (`games.igdb_id`, bigint/nullable/UNIQUE — dedup
  estrutural pro caminho de busca IGDB, Fase 5 do
  `CATALOGO_JOGOS_SPEC.md`) — rodada e validada em produção.
- [x] `services/igdb.py`: OAuth2 client-credentials via Twitch
  Developer (`IGDB_CLIENT_ID`/`IGDB_CLIENT_SECRET` em `.env`, testado
  contra a API real), busca Apicalypse, mapeamento pra
  nome/plataforma/ano/capa.
- [x] Backend: `GET /api/admin/arenas/{id}/wizard-status` resolve o
  checklist on-the-fly (tem_evento, tem_colaborador, tem_branding —
  sem tabela nova, E.1). `POST /api/admin/games` ganha 2 caminhos por
  `igdb_id`: via IGDB pula `pendente_aprovacao` e reaproveita
  duplicata automaticamente (5.1/5.4); manual ganha rate limit 5/dia +
  colisão de nome (5.5/5.6). Vínculo a event só via `event_id`
  explícito — corrige o achado 5.9 (antes poluía todos os events do
  admin).
- [x] Frontend: wizard não-bloqueante de 3 passos em `admin.html` —
  Passo 1 cria event (E.2, default `data_inicio=agora`/
  `data_fim=+10 anos`) **e** resolve jogo na mesma tela (busca IGDB
  com crédito obrigatório "Dados de jogos fornecidos por IGDB.com" —
  5.7 — ou cadastro manual); Passo 2 convidar (E.3, card estático
  apontando pro link `play.html?evento=` que já funciona hoje,
  mecanismo de coadministração fica pra Fase 10); Passo 3 personalizar
  (E.4, paleta de 8 cores pré-definidas + tipografia já fixa em 3
  opções — sem color picker livre, respeita o gate de C.3). Disponível
  também pras Arenas antigas, sem migração extra (G.5).
- [x] Testes: 24 novos (busca IGDB mockada, aprovação automática via
  igdb_id, dedup em reimportação, rate limit/colisão do caminho
  manual, correção do vínculo por `event_id`, wizard-status em
  cenários variados) — 615 passed, 10 failed (baseline conhecido, sem
  banco real).
- [x] Deploy: migração rodada em produção, código commitado (`dc10aea`)
  e push feito.

---

## Fase 10 — Convite assíncrono de colaboradores 🔶 código pronto, aguardando migração em produção

**Spec**: `docs/ARENA_SPEC.md` Fase F, mais H.1
**Depende de**: Fase 8 (reaproveita `memberships`, já renomeada na Fase 7)

**Decisões de implementação fechadas antes de codar** (nível abaixo do
que a `ARENA_SPEC.md` já fecha — acham 3 pontos cegos que a spec de
negócio não detalha):

1. **`user_id` precisa virar nullable.** `memberships.user_id` hoje é
   `NOT NULL` — mas F.2 exige que o convite funcione mesmo pra e-mail
   sem conta ainda (o problema que a Fase F resolve de vez, unificando
   os dois casos "já tem conta"/"não tem conta" num caminho só). Convite
   pendente nasce com `user_id NULL`; só é preenchido no aceite.
2. **Estado `pending` sozinho não sobrevive a cancelamento sem quebrar
   a invariante do token.** Se cancelar só apagasse `token_hash`
   deixando `status='pending'`, a constraint que garante "todo pending
   tem token_hash preenchido" teria que abrir exceção — complica a
   leitura de "é convite pendente de verdade?" em todo lugar que
   consultar a tabela. Solução: 3 estados, não 1 —
   `pending`/`active`/`cancelled`. Cancelar transiciona pra
   `cancelled` (nunca DELETE) e zera `token_hash` (invalida o link).
   `status='pending'` continua significando, sem exceção, "convite
   vivo, token utilizável" — quem lista a fila de convites da Arena
   faz só `WHERE status='pending'`, sem checar mais nada.
3. **Duplicidade de convite pro mesmo e-mail na mesma Arena não vira
   constraint de banco.** O índice único existente
   (`idx_memberships_unico`) já não bloqueia isso sozinho — `NULL` em
   `user_id` nunca colide com outro `NULL` no Postgres, e `now()`
   (pra excluir convite cancelado/expirado do bloqueio) não pode entrar
   num predicado de índice parcial. Mesma opção já usada na Fase 8 pra
   colisão de nome de Arena: checagem em aplicação
   (`buscar_convite_pendente_por_email`) antes do INSERT, não trigger
   nem constraint.

Rate limit H.1 (número não fechado na `ARENA_SPEC.md`, decidido aqui):
**10 convites por Arena/remetente a cada 24h** — mais generoso que o
3/dia de criação de Arena (B.3) porque convidar vários colegas de uma
vez é o caso de uso normal, não abuso; teto ainda existe pra não virar
vetor de spam de e-mail em massa (preocupação central do H.1).

- [ ] Migração 030 (`backend/migrations/030_convites_coadministracao.sql`)
  **escrita, ainda não rodada em produção** — combinado com o Bruno
  rodar manualmente via Supabase SQL Editor (mesmo fluxo das Fases
  7/8/9), não pela sessão diretamente. `user_id` de `memberships` vira
  nullable; ganha `status` (`pending`/`active`/`cancelled`, default
  `active`, decisão #2 acima) e colunas de convite (`email`,
  `invited_by`, `token_hash`, `expires_at`, `accepted_at`) — sem tabela
  nova (F.3). Amplia também o CHECK de `acao` em
  `membership_audit_log` (3 valores novos). Todo o resto desta fase
  (backend/frontend/testes) já está implementado e testado
  (mockado — sem banco real ainda, por depender desta migração rodar
  primeiro), mas só funciona de ponta a ponta depois dela rodar.
- [x] Backend: `POST /api/admin/arenas/{id}/convites` (enviar convite —
  token com hash via o mesmo gerador do magic link, nunca texto puro,
  expira em 7 dias — F.4; rate limit 10/dia por Arena+remetente — H.1);
  `GET .../convites` (listar fila pendente da Arena);
  `PATCH .../convites/{id}/cancelar` (só quem convidou ou super — F.6,
  sem inventar regra nova de quem pode revogar). Router público novo
  `routers/convites.py`: `GET /api/convites/{token}` (preview sem
  login) e `POST /api/convites/{token}/aceitar` (exige e-mail da sessão
  == e-mail convidado, mesma regra de account linking do
  `AUTH_SPEC.md` #2 — F.5; reaproveita `require_authenticated_user`,
  que ficou sem uso desde a Fase 8). Permissão de conceder reaproveita
  `_exigir_admin_na_arena` já existente em `arenas_admin.py` — mesma
  régua de quem pode conceder vínculo direto, sem regra nova (F.6).
  E-mail via Resend (mesmo provedor do `AUTH_SPEC.md` #10).
- [x] **Achado fora do escopo original, corrigido na mesma rodada**:
  `login.html` recebia `next` na URL do magic link (já enviado pelo
  backend desde sempre) mas ignorava e redirecionava sempre pra
  `index.html` — pendência sinalizada, não bloqueante, ao fechar a
  Fase 8. Virou bloqueante aqui: sem isso, F.5 quebraria pra qualquer
  convidado sem sessão ativa que entrasse via Magic Link (login por
  Google já funcionava, o `next` é resolvido no `callback` no backend,
  não no frontend). Corrigido junto.
- [x] Testes: 31 novos (repositório de convite, permissão de
  criar/listar/cancelar, auto-convite bloqueado, colaborador existente
  bloqueado, dedup, rate limit, falha de envio de e-mail não finge
  sucesso, preview público, aceite com e-mail divergente rejeitado,
  convite expirado/cancelado não aceita, corrida de vínculo duplicado
  no aceite) — 656 passed (18 erros de smoke pré-existentes, exigem
  browser/servidor rodando — baseline conhecido, confirmado
  inalterado rodando a suíte antes e depois desta rodada).
- [x] Frontend: Passo 2 do wizard em `admin.html` virou funcional (form
  de convite + fila com cancelar, no lugar do card estático "em
  breve"); `convite.html` novo — preview do convite, aciona login
  (Google ou Magic Link, preservando `?token=`) se necessário, aceita
  e redireciona pro painel.

---

Depois da Fase 10, o restante do `ARENA_SPEC.md` §8 (badges de
rivalidade, chave de campeonato, moderação de score online, corte
grátis/pago em definitivo) segue como pendência registrada, mesmo padrão
do `BACKLOG_2026.md` §5 — sem fase de execução própria ainda, porque
depende de specs futuras que ainda não existem.

---

## Resumo — o que cada fase entrega, de forma independente

| Fase | Entrega sozinha, sem as outras? |
|---|---|
| 1 | Sim — corrige a falha de segurança de `criar_jogo` e formaliza nível, mesmo sem mais nada |
| 2 | Sim, exceto exclusão de conta (precisa da Fase 1 pra trava de titularidade) |
| 3 | Sim, totalmente independente |
| 4 | Não — precisa da Fase 1 (`marca_id NOT NULL`) |
| 5 | Parcial — filtros de data/jogo funcionam sem as outras fases; "sem identificação" precisa da Fase 2; escopo por nível precisa da Fase 1 |
| 6 | Parcial — tudo funciona sem as outras, exceto o prefill de nick/avatar (Fase 2) |
| 7 | Sim — rename puro, zero mudança de comportamento, mas **bloqueia** 8-10 por convenção (não empilhar nomenclatura nova em cima da antiga) |
| 8 | Não — depende inteiramente da Fase 7 (nomenclatura) |
| 9 | Não — depende da Fase 8 (precisa de Arena/evento existindo pra ter o que checar) |
| 10 | Não — depende da Fase 8 (`memberships` só ganha sentido de convite depois da fundação self-serve existir) |

Isso significa que, se for necessário pausar entre fases por qualquer
motivo, o sistema permanece funcional e consistente a cada ponto de parada
— nenhuma fase deixa o produto num estado quebrado esperando a próxima.
