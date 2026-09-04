# Catálogo de jogos: admissão, integração IGDB e jornada de cadastro/seleção

> Status: **Todas as fases fechadas** (1, 2, 3, 4, 5, 6 e 7). Revisa o
> item 3.1 do `docs/BACKLOG_2026.md`
> (decisão anterior: "sem integração externa... processo à parte, fora
> do projeto") — reaberta aqui por pedido explícito, não por
> esquecimento. Nenhuma decisão anterior é tratada como imutável, mesma
> postura já registrada em `ARENA_SPEC.md` A.4.
>
> **Correção de roteiro (2026-09-03)**: as Fases 2 e 3 (§2 abaixo) foram
> fechadas sem que este documento fosse atualizado — o trabalho saiu sob
> o nome "Fase I" e "II.2" de `docs/PAINEIS_ADMIN_SPEC.md` (fechadas em
> 2026-09-01), não sob os nomes de fase daqui. Achado numa análise
> pedida pelo Bruno: os dois roadmaps descreviam a mesma tela (vínculo
> jogo↔evento, fila de aprovação/mesclagem) com nomes de fase
> diferentes, e só um deles foi marcado como concluído. Ver §4/§5 pra
> onde cada decisão de fato vive agora.

---

## 1. Como chegamos aqui

Durante o planejamento de execução da `ARENA_SPEC.md` (Fases 7-10 do
`PLANO_IMPLEMENTACAO_2026.md`), uma pergunta sobre o que vem depois da
Fase 10 levou a avaliar a jornada de cadastro/escolha de jogo — e
encontrou uma lacuna real: a Fase E da `ARENA_SPEC.md` (wizard
pós-ativação, ✅ fechada) promete em E.2 um "aha moment" — link de
ranking funcionando já na primeira sessão — mas não desenha como a
pessoa resolve "qual jogo" nesse momento. Sem jogo vinculado, o link de
ranking não mostra nada.

Investigando o código existente (`admin.py`, migração 018), ficou claro
que cadastro/vínculo de jogo **já funciona**, mas inteiramente dentro do
painel `admin.html` pré-Arena, sem nenhuma ponte com o wizard self-serve,
e sem nenhuma das proteções de admissão que a Fase B da `ARENA_SPEC.md`
desenhou pra Arena (rate limit, colisão de nome, fila de revisão) — apesar
de `games` ser catálogo **global**, compartilhado por toda Arena da
plataforma, com superfície de abuso pelo menos tão grande quanto a de
Arena.

## 2. A jornada mapeada (telas envolvidas)

| Fase | Tela / fluxo | O que resolve |
|---|---|---|
| 1 | Wizard self-serve (`ARENA_SPEC.md` E.2) | Como a pessoa resolve "qual jogo" ao criar a primeira competição — escolher da lista, cadastrar novo ali, ou pular |
| 2 | Painel admin, aba "Jogos" | Cadastro, edição, fila de aprovação, mesclagem de duplicata — revisitado pra população self-serve |
| 3 | Painel admin, aba "Eventos" (vínculo jogo↔evento) | Escolher do catálogo existente, desvincular, reordenar, jogo compartilhado entre eventos/Arenas da mesma pessoa |
| 4 | Lado público (`play.html`, `ranking.html`, `telao.html`) | Comportamento visível pra quem envia score e quem assiste — jogo pendente, jogo mesclado, evento sem jogo nenhum |
| 5 | Admissão e segurança consolidada | Rate limit, dedup, quem revisa a fila — feito **primeiro**, por pedido explícito, porque a integração com a IGDB (ver abaixo) reformula o modelo de admissão que as outras fases vão assumir como já resolvido |

---

## Fase 5 — Admissão e integração com IGDB ✅ fechada

Contexto de pesquisa (não documentado em detalhe nas outras specs porque é
específico desta decisão): IGDB API (`api-docs.igdb.com`) — REST v4,
autenticação OAuth2 client-credentials via Twitch Developer (Client
ID/Secret → token Bearer, validade ~60 dias), rate limit 4 req/s (8
concorrentes), busca via linguagem própria (Apicalypse). **Grátis só pra
uso não-comercial** sob o Twitch Developer Service Agreement — uso
comercial exige parceria negociada à parte (`partner@igdb.com`), não é
plano pago self-serve. Atribuição visível obrigatória em local fixo,
independente do enquadramento comercial. Cache local dos dados retornados
é permitido e incentivado pela própria IGDB.

Decisão sobre o enquadramento comercial: usar agora sob termos
não-comerciais (bate com a realidade atual — sem receita B2B viva, ver
`ARENA_SPEC.md` A.3) e tratar contato com a IGDB pra parceria comercial
como item de ação **quando/se** um plano pago for lançado de verdade
(`ARENA_SPEC.md` C.2/C.3) — dívida técnica/de negócio registrada, não
ignorada.

| # | Tópico | Decisão |
|---|---|---|
| 5.1 | Fonte de verdade / dedup estrutural | `games` ganha coluna nova `igdb_id` (nullable, `UNIQUE` quando preenchida). Jogo vindo da IGDB é ancorado nesse ID externo — dedup deixa de depender de comparação de texto (nome/slug), garantida pelo banco |
| 5.2 | Fluxo de busca no cadastro | Campo de busca dispara Apicalypse contra a IGDB (nome, plataforma, ano, capa), mostra sugestões clicáveis. Ao selecionar: copia os dados pro `games` na criação (cache local, alinhado com a recomendação da própria IGDB) — `plataforma`/`ano_lancamento`/`capa_url` deixam de ser preenchimento manual. `gameplay_url` continua manual (a IGDB não fornece isso) |
| 5.3 | Escape hatch — "não achei na IGDB" | Cadastro manual continua existindo (retrogaming tem título obscuro/homebrew/ROM hack que a IGDB não cobre), mas é o único caminho sem dedup estrutural — carrega todo o peso de admissão abaixo |
| 5.4 | Aprovação automática pro caminho IGDB | Jogo com `igdb_id` preenchido pula `pendente_aprovacao` inteiramente — nasce aprovado, direto no catálogo geral, mesmo vindo de admin não-super. A fila de revisão de `super` (migração 018) passa a existir **só** pro caminho manual — desafoga um gargalo que viraria insustentável em volume self-serve, e é consequência direta de ter fonte externa confiável validando a entrada |
| 5.5 | Rate limit no caminho manual | 5 cadastros manuais/usuário/dia (mais generoso que o 3/dia de Arena — jogo é criado com frequência legítima maior — mas existe, porque é exatamente o caminho sem proteção estrutural). Caminho via IGDB fica **sem** rate limit — abusar dele só adiciona jogos reais já aprovados ao catálogo, sem superfície de dano |
| 5.6 | Colisão no caminho manual | Normalização simples (`lower(trim(nome))`) comparada contra `games.nome` existente — bloqueia duplicata óbvia com sugestão "já existe, quis dizer esse?", mesmo padrão de UX da colisão de nome de Arena (B.2 da `ARENA_SPEC.md`) |
| 5.7 | Atribuição obrigatória | Crédito fixo e visível "Dados de jogos fornecidos por IGDB.com" — rodapé do painel admin (aba Jogos) e qualquer tela pública que exiba capa/metadado vindo de lá (`ranking.html`). Não é negociável, vale mesmo sob uso não-comercial. **Correção (2026-09-03)**: a implementação original só cobria o wizard admin (`admin.html`) — `ranking.html`, a única tela pública que de fato exibe `capa_url` vinda da IGDB, nunca teve o crédito. Achado na revisão de dados IGDB pedida pelo Bruno, corrigido no mesmo dia: `GET /api/ranking/{slug}` passa a devolver `igdb_id` (`repositories/game.py:buscar_por_slug`), e `ranking.html` mostra o crédito só quando o jogo em exibição tem `igdb_id` preenchido (cadastro manual, mesmo com capa preenchida à mão, não credita fonte nenhuma — não veio de lá) |
| 5.8 | Credenciais | Client ID/Secret da Twitch só no backend (`services/igdb.py` novo), nunca expostos ao frontend; token OAuth2 cacheado com renovação antes dos ~60 dias de validade. Variáveis novas em `.env.example` |
| 5.9 | Achado à parte (não é sobre IGDB) — auto-vínculo do jogo novo a todos os eventos do criador | Comportamento atual (`admin.py`, criação de game) vincula um jogo recém-criado a **todos** os eventos que o admin tem acesso, não só ao que estava editando. Fazia sentido com poucos admins/poucos eventos; em escala self-serve (uma pessoa dona de várias Arenas/eventos) polui eventos sem relação com o jogo criado. Passa a vincular só ao evento em contexto — precisa de parâmetro `event_id` explícito no endpoint de criação |

---

## Fase 1 — Wizard self-serve ✅ fechada

Construída junto com a Fase 9 do `PLANO_IMPLEMENTACAO_2026.md` — as duas
são a mesma tela (Passo 1 do wizard resolve evento **e** jogo juntos).
Ver detalhamento completo no registro da Fase 9. Resumo: busca na IGDB
com crédito obrigatório (5.7), cadastro manual como escape hatch (5.3),
`event_id` explícito evita poluir outros eventos do mesmo admin (achado
5.9, corrigido nesta rodada).

## Fase 2 — Painel admin, aba "Jogos" (fila de aprovação/mesclagem) ✅ fechada

Fechada em 2026-09-01 sob o nome **II.2** de `docs/PAINEIS_ADMIN_SPEC.md`,
não sob este nome de fase — ver a nota de correção de roteiro no topo
deste documento. Migrou pra `console.html` (super-only, não mais
`admin.html`): fila de `games.pendente_aprovacao=true` com "aprovar como
novo" ou "mesclar com existente" (`POST /api/admin/games/{id}/mesclar`,
transacional, nunca deleta — soft-archive via `ativo=false` +
`mesclado_em_game_id`), e edição de metadado do catálogo global
(plataforma/ano/capa/gameplay/score_max/ativo — nome/slug **não** eram
editáveis nesta fase; ver §Fase 6 abaixo).
Implementação: `backend/repositories/game.py` (`listar_pendentes_aprovacao`,
`aprovar`, `mesclar`), `backend/routers/admin.py:500-557`,
`frontend/console.html` (aba Catálogo).

## Fase 3 — Painel admin, vínculo jogo↔evento ✅ fechada

Fechada em 2026-09-01 sob o nome **Fase I** de
`docs/PAINEIS_ADMIN_SPEC.md` (I.1-I.4), não sob este nome de fase — ver a
nota de correção de roteiro no topo deste documento. Aba "Jogos" de
`admin.html`, escopada corretamente por arena
(`_exigir_admin_na_arena`, corrigindo o achado 1 daquela spec: o toggle
antigo mexia no catálogo global em vez do vínculo do evento). Cobre
busca no catálogo existente pra adicionar ao evento, ativar/desativar o
vínculo (não o jogo global), e reordenar com setas ↑/↓. Implementação:
`backend/repositories/event_game.py`, `backend/routers/events.py:153-205`,
`frontend/admin.html` (`carregarJogos`/`renderJogos`).

## Fase 6 — Edição de nome/slug no catálogo global ✅ fechada (2026-09-03)

Achado numa análise pedida pelo Bruno: `PATCH /api/admin/games/{id}`
nunca aceitou `nome`/`slug` — a única forma de corrigir um typo era
recriar o jogo certo e mesclar o errado nele (`POST
/api/admin/games/{id}/mesclar`), o que funciona mas é desproporcional
pra um erro de digitação e **perde o slug original** (a mesclagem
mantém o slug do destino, não do jogo com o nome corrigido). Decisão:

| # | Tópico | Decisão |
|---|---|---|
| 6.1 | Quem edita | Mesmo gate de sempre — só super (`_exigir_super_editar_game`, AA.2). Sem gate novo |
| 6.2 | Colisão de nome na edição | Reaproveita `services/game_admissao.avaliar_colisao` (5.6), mas excluindo o próprio game da lista de "existentes" — senão qualquer edição de nome colidiria consigo mesmo |
| 6.3 | Colisão de slug | Sem checagem de aplicação — a coluna já tem `UNIQUE NOT NULL` desde `001_initial.sql`; violação vira 409, mesmo padrão de erro já usado em `criar_game` |
| 6.4 | Limitação conhecida, não corrigida aqui | O critério de colisão de 5.6 é substring (`cand in exist or exist in cand`), o que bloqueia renomear pra um nome que é prefixo de outro já existente (ex.: corrigir pra "Sonic" com "Sonic Advance" já cadastrado). Pré-existente ao cadastro (já valia pra criação manual), só herdado aqui — corrigir a heurística é decisão maior que afeta Arena (B.2) também, fora do escopo deste item |

Implementação: `backend/repositories/game.py` (`atualizar`, `listar_nome_ativos`
ganha `id`), `backend/routers/admin.py` (`AtualizarJogo`, `atualizar_game`),
`frontend/console.html` (aba Catálogo).

## Fase 4 — Lado público ✅ fechada (2026-09-03)

Investigação (análise pedida pelo Bruno) achou dois cenários distintos
do que a Fase 5 do roadmap original (§2) chamava de "jogo pendente/
mesclado, evento sem jogo nenhum" — só um dos dois exigia mudança:

| # | Cenário | Situação encontrada | Decisão |
|---|---|---|---|
| 4.1 | Evento/telão sem nenhum jogo aprovado ainda | **Bug real, silencioso.** `play.html` já tratava isso (`renderJogos([])` → "Nenhum jogo disponível", `frontend/play.html:1140-1141`). `ranking.html` e `telao.html` **não**: `game-tabs`/`tv-tabs` renderizam vazio (`games.map(...)` sobre array vazio) e `ranking-grid`/`tv-ranking` nunca saem do esqueleto "CARREGANDO..." inicial, porque `selecionarJogo`/`mudarJogo` só é chamado se houver ao menos 1 game — página trava numa tela de loading eterno, sem explicar o que houve | Adiciona estado vazio explícito nas duas telas, reaproveitando o padrão `.empty-state` que `ranking.html` já usa pra outros vazios (sem score, sem resultado de busca, erro de conexão) — não é padrão novo, só um caso a mais do que já existe |
| 4.2 | Jogo mesclado enquanto alguém está com `play.html` aberto (`game_id` antigo em memória) | **Falso alarme — já coberto.** `services/score.py:validar_score` já faz `WHERE id = $1 AND ativo = true` — `mesclar()` desativa a origem (`ativo=false`), então o envio com `game_id` obsoleto recebe 404 "Jogo não encontrado ou inativo" do backend, sem gravar nada incorreto. O frontend (`play.html:1406-1411`) já propaga `data.detail` pro toast de erro. Não é elegante (não sugere "recarregue a página"), mas não é um bug de integridade — não justificava trabalho novo isolado | Nenhuma mudança — documentado aqui pra fechar o item do roadmap, não deixar como pendência não investigada |

Implementação de 4.1: `frontend/ranking.html` (`carregarJogos`, novo
`renderSemJogo`), `frontend/telao.html` (`carregarConfigTelao`, mesmo
padrão adaptado ao tema do telão).

## Fase 7 — Metadado de busca: gênero e geração de plataforma (2026-09-03)

Motivada por queixa de usabilidade no canto "Jogos"
(`docs/PAINEIS_ADMIN_SPEC.md` §10): buscar jogo hoje só filtra por
nome. Pedido do Bruno: filtrar também por gênero (ex: "jogos de luta"),
geração de console (ex: "3ª geração") — ano já dava pra filtrar
(`ano_lancamento` já existe). Pesquisa no schema oficial da IGDB
(verificado contra a definição de campos real, não por suposição)
confirma disponibilidade:

| Campo desejado | Campo IGDB | Onde mora | Multiplicidade |
|---|---|---|---|
| Gênero | `game.genres` → `genre.name` (ex: "Fighting", "Platform") | No jogo | Vários por jogo |
| Geração de console | `platform.generation` (inteiro) | Na **plataforma**, não no jogo | Um jogo pode ter várias plataformas, cada uma com sua geração |
| Ano | `game.first_release_date` | No jogo | Já temos (`ano_lancamento`) |

### Decisões

| # | Tópico | Decisão |
|---|---|---|
| 7.1 | Novas colunas em `games` | `generos text[]` e `geracoes integer[]`, ambas nullable, sem índice — dataset pequeno hoje (12 jogos em produção), mesmo raciocínio já aplicado a `plataforma`/`ano_lancamento` (sem índice) |
| 7.2 | Por que array nativo, não tabela de junção | Mesmo nível de simplicidade que o resto do catálogo já usa (`plataforma` é string livre, não FK pra uma tabela de plataformas). `text[]`/`integer[]` dá `WHERE 'Fighting' = ANY(generos)` sem tabela nova nem JOIN — volume do catálogo (dezenas de jogos, não milhares) não justifica a complexidade extra |
| 7.3 | Geração — um jogo, várias plataformas, várias gerações | `geracoes` guarda o **conjunto**, não um valor só — ex.: Street Fighter II saiu em Arcade e SNES, gerações diferentes; filtrar "3ª geração" deve achar o jogo se **qualquer** plataforma dele for gen 3 |
| 7.4 | Cadastro manual (sem IGDB) | Sem gênero/geração — mesma régua de sempre: esses campos só vêm de fonte estruturada (IGDB); cadastro manual continua com metadado mínimo, sem obrigar o admin a digitar taxonomia |
| 7.5 | Onde filtra | Cliente (JS), sobre o catálogo já carregado em `admin-jogos.html` (`games-todos` já traz tudo pra lá) — sem endpoint novo, sem paginação server-side. Reavaliar se o catálogo crescer de dezenas pra centenas |
| 7.6 | Edição manual de gênero/geração no catálogo global | **Fora desta rodada.** Super já edita plataforma/ano/capa/etc (Fase 6), mas gênero/geração "vêm de fora" — editar à mão abriria inconsistência de taxonomia sem curadoria nenhuma. Gap consciente, não esquecido |

### Migração 031 — o que muda, em português simples

**O que muda**: 2 colunas novas em `games` — `generos` (lista de
textos, ex.: `{Fighting, Action}`) e `geracoes` (lista de números, ex.:
`{3, 4}`). Nenhuma tabela nova, nenhuma constraint nova.

**É reversível?** Sim — `DROP COLUMN` desfaz sem efeito colateral em
nenhuma outra tabela (nada referencia essas colunas via FK).

**Afeta dado existente?** Não — as 2 colunas nascem `NULL` em todo jogo
já cadastrado (nenhum dos 12 jogos em produção tem esse dado hoje,
porque o campo nunca existiu). Sem backfill necessário; jogos antigos
simplesmente não aparecem em filtro de gênero/geração até serem
recadastrados via IGDB — ninguém pediu re-sync em massa, fora de
escopo.

**Validado contra o Postgres de produção** (mesmo processo da Fase 0 do
`PAINEIS_ADMIN_SPEC.md`): conectado via `DATABASE_URL` (só leitura
antes de rodar), confirmado o schema atual de `games` e a contagem real
(12 jogos) — dataset pequeno, migração de baixíssimo risco.

Implementação: `backend/migrations/031_generos_geracoes_jogos.sql`,
`backend/services/igdb.py` (Apicalypse pede `genres.name`/
`platforms.generation`, `_mapear_resultado` extrai e agrega),
`backend/repositories/game.py` (`criar`/`atualizar`/todas as SELECT),
`backend/routers/admin.py` (`CriarJogo`/`AtualizarJogo`),
`frontend/admin-jogos.html` (filtro por gênero/geração na busca de jogo
existente, badges nos resultados da IGDB).
