# Catálogo de jogos: admissão, integração IGDB e jornada de cadastro/seleção

> Status: Fases 1-7 fechadas, **Fase 8 implementada** (§8 abaixo),
> **pendente de validação manual em navegador** — enriquecimento de
> metadado do card + resync dos jogos já cadastrados contra a IGDB,
> motivado por pedido do Bruno em 2026-09-04. Revisa o
> item 3.1 do `docs/BACKLOG_2026.md`
> (decisão anterior: "sem integração externa... processo à parte, fora
> do projeto") — reaberta aqui por pedido explícito, não por
> esquecimento. Nenhuma decisão anterior é tratada como imutável, mesma
> postura já registrada em `ARENA_SPEC.md` A.4.
>
> **Fase 9 implementada** (§9 abaixo), **pendente de validação manual em
> navegador** (mesma ressalva de sempre, [[project_sandbox_env_constraints]])
> — fim do reorder manual jogo↔evento, ordenação por critério movida pra
> aba "Event" do `admin.html`, aba "Games" duplicada aposentada.
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

---

## 8. Fase 8 — Enriquecimento de metadado do card + resync do catálogo existente (2026-09-04)

Motivada pelo Bruno depois de ver a listagem nova do §11 do
`PAINEIS_ADMIN_SPEC.md`: "cada card tem que trazer todas as informações
referentes ao jogo... quero identificar quais as informações existentes
na IGDB pra melhorar o card". Inclui pedido explícito de resync — os 12
jogos já cadastrados (a maioria via IGDB desde a Fase 5, alguns
manuais) podem ser reencontrados na IGDB pra atualizar campos e imagens
(capa e "imagens de gameplay para referência").

### 8.1 Achado que corrige o registro

O §5.2 deste documento afirma que "a IGDB não fornece" imagem de
gameplay — **isso é factualmente errado**, verificado agora contra o
schema real da IGDB (tipos oficiais, não suposição, mesma disciplina do
§7): a IGDB tem `screenshots[]` (capturas reais do jogo rodando) e
`videos[]` (trailers/gameplay, ID de vídeo do YouTube) por jogo, desde
sempre. A decisão original nunca foi verificada contra o schema —
ficou base pra `gameplay_url` ser 100% manual até hoje.

### 8.2 Achado do bug de busca (§11.3 do PAINEIS_ADMIN_SPEC.md, retomado)

Testado agora `services/igdb.buscar()` diretamente contra a IGDB real
(credenciais de `backend/.env`, mesma função que a rota usa) — **funciona
normalmente**, resultado real pra "street fighter" com capa/gênero/geração
corretos. Ou seja: credenciais, Apicalypse e mapeamento não estão
quebrados. O bug real é de **UX de diagnóstico**, achado lendo
`admin-jogos.html`:

- `buscarIgdb()` (linha ~580) trava `igdbIndisponivel = true` na
  **primeira** resposta 503 (rede instável, rate limit da IGDB, timeout)
  e nunca reseta sozinho — só um reload de página desfaz. O toast
  "Busca por jogo indisponível" só aparece **nessa primeira vez**; toda
  tentativa seguinte na mesma sessão do navegador (linha 582, `if
  (igdbIndisponivel) return`) sai **sem nenhum feedback visual** — parece
  que a busca simplesmente não faz nada, não que "está indisponível".
  Isso bate exatamente com a queixa "nenhuma das minhas tentativas
  encontrou resultado" — uma falha transitória isolada (rede, rate
  limit) trava a sessão inteira sem avisar de novo.
- Reforça: qualquer resposta não-200 e não-503 (erro 500, JSON
  malformado) cai no mesmo `catch`/`if (!resp.ok)` que também limpa o
  container **sem toast nenhum** — indistinguível de "não achei nada
  pra esse nome".

| # | Tópico | Decisão |
|---|---|---|
| 8.B1 | Latch de indisponibilidade | Vira temporário (ex.: 30s) em vez de "pro resto da sessão" — uma falha transitória não deve exigir reload de página pra tentar de novo |
| 8.B2 | Feedback em toda falha | Toast de indisponibilidade aparece **toda vez** que uma busca falha (rede/503/erro inesperado), não só na primeira — nunca mais silencioso |
| 8.B3 | Diagnóstico no backend | `services/igdb.py` passa a logar o status HTTP e corpo da resposta de erro da IGDB/Twitch (hoje só loga a exceção genérica) — se acontecer de novo em produção, dá pra saber a causa real pelos logs do Railway em vez de reproduzir manualmente |

### 8.3 Campos novos — decisão fechada com o Bruno

| Campo IGDB | Coluna nova em `games` | Exibição |
|---|---|---|
| `summary` | `resumo text` | Só no detalhe expandido |
| `involved_companies` (`developer`/`publisher`) | `desenvolvedora text`, `publicadora text` (join por vírgula se mais de uma empresa, mesmo padrão de `plataforma`) | Só no detalhe expandido |
| `game_modes[].name` | `modos_jogo text[]` | Só no detalhe expandido |
| `multiplayer_modes` (achatado das flags booleanas) | `modos_multiplayer text[]` (ex.: `{Co-op offline, Split-screen, Online}`) | Só no detalhe expandido |
| `franchises[].name` (+ `franchise` principal) | `franquias text[]` | Só no detalhe expandido |
| `total_rating` (média ponderada de usuários+crítica IGDB — mais estável que `rating` isolado) | `rating_igdb smallint` (0-100, arredondado) | Só no detalhe expandido, **rotulado "Nota IGDB"**, nunca ao lado do ranking real da plataforma — ver 8.4 |
| `age_ratings` (achatado `organization.name: rating_category.rating`) | `classificacoes_etarias text[]` (ex.: `{"ESRB: T", "PEGI: 12"}`) | Só no detalhe expandido |
| `screenshots[0].image_id` (primeira só, por pedido do Bruno) | `screenshot_url text` | Só no detalhe expandido |
| `keywords[].name` | `palavras_chave text[]` — **não exibido**, só amplia o filtro local de texto (`renderResultadosCatalogo`) | — |
| `alternative_names[].name` | `nomes_alternativos text[]` — **não exibido**, mesmo uso (achar "Rockman" buscando por "Megaman") | — |
| `themes`, `player_perspectives`, `artworks` | **Fora** — redundante com gênero (themes) ou baixo valor pro catálogo retro/luta (perspectiva/arte promocional), decisão do Bruno | — |

Card da **listagem** (`resultado-card`) continua enxuto — nome, capa,
badges de gênero/geração, como está desde o §11 do
`PAINEIS_ADMIN_SPEC.md`. Os campos acima só aparecem ao expandir um
jogo específico (decisão do Bruno: evita pesar a listagem de até 60
itens com resumo/galeria/etc de cada um).

### 8.4 Por que `rating_igdb` é isolado e rotulado

Risco de produto identificado: a plataforma vende "ranking dos seus
próprios jogadores" como proposta de valor central
([[project_arena_pivot]]). Importar e exibir a nota de crítica/usuário
de **outra** plataforma, sem deixar clara a origem, dilui essa proposta
— pareceria que o "rating" do jogo é parte do produto, quando é
metadado de terceiro copiado por curadoria. Mitigação: nome de coluna
(`rating_igdb`, nunca `rating`/`nota` puro), rótulo fixo "Nota IGDB" na
UI, e nunca no mesmo componente visual que mostra o ranking de scores
reais de um evento.

### 8.5 Migração de dados dos 12 jogos existentes (resync)

| # | Tópico | Decisão |
|---|---|---|
| 8.5.1 | Escopo | Todo jogo do catálogo (`games`), IGDB ou manual, ganha ação "Atualizar da IGDB" no detalhe expandido (super-only, mesmo gate de edição do catálogo global, Fase 6) |
| 8.5.2 | Jogo já ancorado (`igdb_id` preenchido) | Resync direto: busca por ID (`GET .../games` com `where id = igdb_id`), sem ambiguidade — sobrescreve **todos** os campos de origem IGDB (inclusive os já existentes: plataforma/ano/capa/gênero/geração), nunca `nome`/`slug` (editorial, Fase 6, decisão do Bruno de sempre preservar controle manual sobre identidade do registro) |
| 8.5.3 | Jogo manual (`igdb_id` nulo) | Busca por nome (`services.igdb.buscar`) e **sempre** apresenta candidato(s) pro super escolher antes de aplicar — nunca decide sozinho qual jogo da IGDB corresponde, mesmo com 1 resultado só (pedido explícito do Bruno: "se ficar em dúvida... me pergunte" — tratado aqui como "sempre confirmar", já que vincular `igdb_id` errado a um jogo manual existente seria pior que não vincular: contaminaria o catálogo com metadado do jogo errado) |
| 8.5.4 | Zero resultado na busca por nome (manual) | Fica como está — sem IGDB pra ancorar, super decide se corrige o nome e tenta de novo ou deixa manual mesmo |
| 8.5.5 | Endpoint | `POST /api/admin/games/{id}/resync-igdb` novo — não reaproveita `PATCH /games/{id}` porque a semântica é diferente (busca+substitui em massa vs. edição pontual de um campo) |

### Implementação

- [x] Migração 032 (`backend/migrations/032_enriquecimento_igdb_jogos.sql`)
  — aplicada em produção em 2026-09-04 (leitura antes/depois confirmou
  12 jogos preservados, colunas novas nascendo `NULL`, mesmo processo de
  validação da Fase 0 do `PAINEIS_ADMIN_SPEC.md`)
- [x] `backend/services/igdb.py`: campos leves (`_CAMPOS_LEVES`, busca
  por nome, sem mudança de payload) separados dos completos
  (`_CAMPOS_COMPLETOS`, só buscados sob demanda via `buscar_por_id`) —
  `_mapear_detalhe` extrai/achata tudo (`total_rating`→`rating_igdb`,
  `age_ratings` via enums flat category/rating→`classificacoes_etarias`,
  `multiplayer_modes`→`modos_multiplayer`). Testado contra a IGDB real
  (credenciais de `backend/.env`) antes de escrever os testes mockados —
  `Street Fighter III: 3rd Strike` (id 6710) confere: resumo, Capcom
  como dev/publisher, franquia, nota 86, screenshot, todos corretos
- [x] Correção do bug de UX (8.2/8.B1-8.B3): `igdbIndisponivel` (latch
  permanente) virou `igdbIndisponivelAte` (cooldown de 30s), toast em
  toda falha (503, não-2xx, exceção de rede), backend loga status+corpo
  da resposta de erro da IGDB
- [x] `POST /api/admin/games/{id}/resync-igdb` (8.5.5) — resync direto
  por `igdb_id` quando já ancorado, candidatos por nome + confirmação
  obrigatória quando manual (8.5.3), 409 se o `igdb_id` escolhido já
  ancora outro game do catálogo
- [x] Detalhe expandido do card em `admin-jogos.html` (8.3) — botão
  "▾ Detalhes" por jogo, "Nota IGDB" sempre rotulada e isolada (8.4),
  botão "Atualizar da IGDB" só pra super (`souSuper()`, mesmo gate do
  backend)
- [x] Testes novos: `test_igdb_service.py` (+6, mapeamento de detalhe +
  log de erro HTTP), `test_admin_games_resync.py` (+8, os 3 caminhos do
  endpoint + 403/404/409/503). Suíte completa: 716 passando
  (`pytest tests/ --ignore=tests/smoke`)
- [x] `log.warning("igdb_nao_configurado")` — achado em produção
  2026-09-05: era o único caminho de erro do módulo que não logava
  nada, dificultou diagnosticar um 503 causado por credencial ainda
  vazia (`get_settings()` é `@lru_cache` — processo já de pé antes da
  env var ser setada no Railway continua com o valor antigo até reiniciar)
- [x] Capa/screenshot clicável (lightbox, `imgAmpliavel`/`abrirLightbox`)
  — pedido do Bruno pra conseguir ver a capa ampliada (resolução
  `t_original` da IGDB, não só esticada por CSS) antes de confirmar um
  candidato de resync (8.5.3)
- [x] Indicador de carregando na busca IGDB (`marcarCarregandoIgdb`) +
  resultado/candidatos ordenados do mais antigo pro mais novo
  (`ordenarPorAnoAntigo`) — original tende a ser o candidato certo, não
  remaster/relançamento no meio da lista
- [ ] Validação manual em navegador — pendente (mesma ressalva de
  sempre, [[project_sandbox_env_constraints]])

### 8.6 Incidente real em produção (2026-09-05) — duplicata do River Raid

Sequência de achados testando a Fase 8 em produção pela primeira vez,
todos no mesmo dia:

1. **Slug colidindo sem desambiguar**: `selecionarJogoIgdb()` gerava o
   slug só a partir do nome — nome repetido entre jogos diferentes é
   comum na IGDB (ex.: "Donkey Kong" tem registro separado pro arcade
   original e pra versão de Game Boy), e ao colidir com slug já em uso
   o `POST /games` inteiro falhava com 409, sem cadastrar nem vincular
   nada. Corrigido: desambigua com ano de lançamento (ou `igdb_id` sem
   isso) antes de tentar.
2. **Duplicata real com dado de produção**: a correção acima resolveu
   o 409, mas expôs um problema pior — dedup por `igdb_id` (5.1) não
   cobre jogo manual com o **mesmo nome**. Resultado real: "River Raid"
   manual (15 recordes de jogador reais + vínculo a evento ativo desde
   2026-03) e um "River Raid" novo via IGDB viraram dois registros
   separados no catálogo. Corrigido nos dois níveis:
   - **Dado já duplicado**: mesclado via `POST /games/{id}/mesclar`
     (origem = manual antigo com os 15 recordes, destino = novo com
     metadado da IGDB) — 15 recordes e o vínculo de evento migrados,
     origem arquivada (nunca apagada). Efeito colateral conhecido, não
     é bug novo: o vínculo antigo (`event_games`) continua aparecendo
     em "Vinculados a este evento" no admin com selo "Oculto
     globalmente" — `listar_por_event_admin` mostra vínculo mesmo de
     jogo desativado globalmente, de propósito (Fase I do
     `PAINEIS_ADMIN_SPEC.md`), pra dar chance de reverter uma
     desativação por engano.
   - **Prevenção**: `buscarIgdb()` agora avisa (`acharNoCatalogoPorNome`,
     comparação simples case/trim-insensitive) quando o nome do
     resultado da IGDB já existe no catálogo, sugerindo "Atualizar da
     IGDB" no registro existente em vez de cadastrar outro. Não
     bloqueia — vira botão "Cadastrar mesmo assim", já que nome igual
     pode legitimamente ser jogo diferente (ex.: duas versões de
     "Frogger" bem distintas entre si).

Nenhuma migração nova — mudança de comportamento em
`frontend/admin-jogos.html` e uma mesclagem pontual de dado via
`repositories.game.mesclar` (mesma função já usada pelo console.html,
chamada aqui direto contra produção, mesmo processo de leitura+ação
autorizada usado pra migração 032).

---

## 9. Fase 9 — Ordenação por critério e fim do vínculo duplicado (2026-09-05)

Motivada pelo Bruno questionando por que `admin-jogos.html` mostra o
catálogo inteiro (já indicando "✓ Vinculado" por jogo) **e** uma segunda
lista "Vinculados a este evento" logo abaixo — pareceu redundante.
Investigando o motivo real da segunda lista (não só aceitar a proposta
de juntar as duas, ver postura crítica do `CLAUDE.md`), achou-se que ela
não é só um espelho do catálogo: é o único lugar que edita **ordem**
(setas ↑/↓) e **ativo/inativo no evento** — e reordenar jogo a jogo
misturado numa lista alfabética/filtrável/paginada em 60 itens (a do
catálogo) não faz sentido (não há "vizinho" visível pra comparar quando
o catálogo está filtrado).

### 9.1 Achados que mudaram o escopo original do pedido

| # | Achado | Onde |
|---|---|---|
| 9.A1 | `frontend/admin.html` tem uma aba "Games" com implementação **própria e independente** do mesmo vínculo jogo↔evento (busca/adicionar, ↑/↓, toggle ativo) — não é código morto, é uma aba viva (`data-tab="games"`). Historicamente já causou confusão de tracking (ver nota de correção de roteiro no topo deste doc: mesma tela, dois nomes de fase, um marcado concluído e o outro não) | `frontend/admin.html:742,1659-1917` |
| 9.A2 | `event_games.ordem` não é só um detalhe de exibição do admin — a home pública (`index.html`) usa o **primeiro jogo por ordem** de cada evento como "jogo em destaque" no card do evento | `frontend/index.html:369-379`, `backend/repositories/event_game.py` (`ORDER BY ej.ordem, j.nome`) |
| 9.A3 | `telao_jogos.ordem` é uma ordenação **separada e independente** de `event_games.ordem` (comentário no próprio código) — fora do escopo desta fase | `backend/routers/teloes_admin.py:7` |
| 9.A4 | A ação "Arquivar ranking" que só existia dentro da aba Games do `admin.html` já existe, duplicada, em `console.html` (super-only) — retirar a aba não tira essa capacidade de ninguém | `frontend/console.html:190-199` |

### 9.2 Decisões fechadas com o Bruno

| # | Tópico | Decisão |
|---|---|---|
| 9.1 | Reorder manual (↑/↓) | **Sai de vez**, em `admin-jogos.html` e em `admin.html`. Vira só critério automático — aceito o efeito colateral do achado 9.A2 (a home passa a destacar "o jogo que vier primeiro pelo critério escolhido", não mais uma curadoria manual por evento) |
| 9.2 | Critérios disponíveis | Alfabética (nome), ano de lançamento, plataforma, e "mais pontuações" — desempate sempre por nome, mesmo padrão já usado em `ORDER BY ej.ordem, j.nome` |
| 9.3 | O que conta em "mais pontuações" | Só entries **válidas** (`pendente=false AND no_ranking=true`) do jogo **naquele evento** — reflete popularidade real no ranking público, não volume bruto de envio (que inclui pendente de moderação/oculto) |
| 9.4 | Onde mora a ação de ordenar | Na aba "Event" (config) de `admin.html`, junto dos outros ajustes por evento (`publico`, `modo_ranking`, janela de envio) — é uma propriedade do evento, não uma ação por jogo. **Não** vira tela nova, **não** fica em `admin-jogos.html` |
| 9.5 | Implementação (por quê) | Sem migração: `event_games.ordem` continua existindo e sendo lido por todo mundo (admin, home) exatamente como hoje — a ordenação por critério é uma ação em lote que **recalcula e regrava `ordem`** de uma vez pra todos os jogos do evento, não uma leitura dinâmica espalhada pelo código. Endpoint novo `POST /api/admin/events/{event_id}/games/ordenar` |
| 9.6 | Aba "Games" do `admin.html` | Aposentada — removida (busca/adicionar/reorder/toggle/arquivar). O vínculo jogo↔evento passa a viver só em `admin-jogos.html`, elimina a duplicação do achado 9.A1 |
| 9.7 | `admin-jogos.html` — bloco "Vinculados a este evento" | Removido — sem função exclusiva depois que a ordenação sai (9.1) e o toggle ativo/inativo é absorvido pelo próprio card do catálogo (troca o badge estático "✓ Vinculado" por um controle interativo) |

### 9.3 Consequência aceita explicitamente

Depois desta fase, **não existe mais curadoria manual de ordem** —
nem por jogo (setas), nem por evento (só os 4 critérios). Quem cuidava
de qual jogo aparecia primeiro no card de destaque da home (achado
9.A2) passa a depender do critério escolhido pra aquele evento. Aceito
pelo Bruno como troca válida pela simplicidade.

### Implementação

- [x] `backend/repositories/event_game.py`: `reordenar_por_criterio(pool,
  event_id, criterio)` — recalcula `ordem` de todos os `event_games` do
  evento (ativos e inativos) por `nome`/`ano_lancamento`/`plataforma`/
  contagem de entries válidas, desempate por nome, grava em lote
- [x] `backend/routers/events.py`: `POST
  /api/admin/events/{event_id}/games/ordenar` (`{criterio: "nome" |
  "ano" | "plataforma" | "pontuacoes"}`), mesmo gate de edição do
  vínculo (`_exigir_admin_na_arena`). Achado no caminho: precisa vir
  **antes** de `POST /{event_id}/games/{game_id}` no arquivo — senão
  "ordenar" é capturado como `game_id` (FastAPI casa rotas na ordem
  declarada), pego pelos testes antes de chegar em produção
- [x] `frontend/admin.html`: aba "Event" ganha controle "Ordenar jogos
  por…" + aplicar, por evento (`CRITERIOS_ORDENAR_JOGOS`,
  `ordenarJogosDoEvento`); aba "Games" inteira removida (botão,
  `tab-content`, `carregarJogos`/`renderJogos`/busca/reorder/arquivar) —
  link pra `admin-jogos.html` adicionado na aba Event, já que é lá que
  vincular/ativar jogos passa a acontecer
- [x] `frontend/admin-jogos.html`: bloco "Vinculados a este evento"
  removido; card do catálogo ganha toggle ativo/inativo (`.toggle-ativo`)
  no lugar do badge estático "✓ Vinculado" quando já vinculado
- [x] Testes novos pro endpoint de ordenação: critério válido,
  critério desconhecido (422 via `Literal` do Pydantic), moderador
  bloqueado (403), cross-arena bloqueado (403) — suíte completa em
  720/720 (`pytest tests/ --ignore=tests/smoke`)
- [x] Validação da query de ordenação contra Postgres real de **produção**
  (autorizado pelo Bruno, só leitura — SELECT sem UPDATE) — rodada contra
  o evento real "Canal3 Expo" (9 jogos vinculados, incluindo o "River
  Raid" duplicado/arquivado do incidente §8.6, ainda vinculado como
  "Oculto globalmente"): os 4 critérios produzem sequência 0..N-1
  contígua, sem perder nem duplicar linha, desempate por nome correto em
  todos. UPDATE de verdade não foi executado nessa validação — primeira
  vez que a feature roda de fato será via uso real no admin
