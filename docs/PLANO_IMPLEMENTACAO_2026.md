# Plano de Implementação — Backlog 2026

> Todas as decisões de arquitetura estão fechadas (ver `docs/BACKLOG_2026.md`
> e os 5 documentos referenciados nele). Este documento organiza **a ordem
> de execução** — por dependência real entre as peças, não pela ordem em
> que discutimos. Nenhuma fase começa antes da anterior estar validada em
> produção, seguindo o mesmo processo já usado no projeto inteiro: migração
> testada localmente → aplicada → backend → testes → frontend → validação.

Próxima migração livre: **`026`**.

**Fase 1 concluída** (migração 019, ver `docs/PERMISSOES_SPEC.md` §7).
**Fase 2 concluída** (migrações 020-022, ver `docs/NICKNAME_SPEC.md` e
`docs/EXCLUSAO_CONTA_SPEC.md`). **Fase 3 concluída** (migração 023, ver
`docs/SEGUIR_SPEC.md`). **Fase 4 concluída** (migrações 024-025, ver
`docs/RANKINGS_CONFIGURAVEIS_SPEC.md`). **Fase 5 concluída** (sem
migração — extensão pura de `WHERE`, nenhuma mudança de schema, ver
`docs/BACKLOG_2026.md` §4). **Fase 6 concluída** (sem migração —
`frontend`/`marcas_publico` novo endpoint público, sem schema novo, ver
`docs/BACKLOG_2026.md` §2/§3.4). Todas aplicadas em produção, backend e
frontend prontos. Backlog do plano original está completo — próximos
itens vêm de `docs/BACKLOG_2026.md` §5 (pendências registradas, sem
ordem de execução fechada ainda).

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

## Resumo — o que cada fase entrega, de forma independente

| Fase | Entrega sozinha, sem as outras? |
|---|---|
| 1 | Sim — corrige a falha de segurança de `criar_jogo` e formaliza nível, mesmo sem mais nada |
| 2 | Sim, exceto exclusão de conta (precisa da Fase 1 pra trava de titularidade) |
| 3 | Sim, totalmente independente |
| 4 | Não — precisa da Fase 1 (`marca_id NOT NULL`) |
| 5 | Parcial — filtros de data/jogo funcionam sem as outras fases; "sem identificação" precisa da Fase 2; escopo por nível precisa da Fase 1 |
| 6 | Parcial — tudo funciona sem as outras, exceto o prefill de nick/avatar (Fase 2) |

Isso significa que, se for necessário pausar entre fases por qualquer
motivo, o sistema permanece funcional e consistente a cada ponto de parada
— nenhuma fase deixa o produto num estado quebrado esperando a próxima.
