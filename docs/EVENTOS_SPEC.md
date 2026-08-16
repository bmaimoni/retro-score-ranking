# Eventos, Placares, Telões e Paginação — Retro Score Ranking

> Status: **decisões fechadas, pronto para commit**. Substitui e expande a
> §8 (Multi-evento) do `SPEC.md`, que deve ser atualizada para apontar pra
> este documento quando isso for implementado.

---

## 1. Objetivo

O desenho atual de eventos (Migration 010) foi construído supondo **um
evento ativo por vez** e um único telão fixo por evento. Isso não aguenta:

1. **Eventos simultâneos** — dois eventos rodando ao mesmo tempo, cada um
   recebendo envios próprios.
2. **Janela de envio independente de visibilidade** — um evento pode ficar
   acessível/consultável para sempre, mas parar de aceitar novos scores
   depois de uma data.
3. **Todo score vinculado a um evento** — sem exceção, sem "adivinhação".
4. **Placares além do por-evento** — um placar geral (todos os eventos) e
   placares customizados (Hall da Fama a partir de uma seleção específica de
   eventos).
5. **Múltiplos telões** — não é mais "1 evento = 1 telão"; um telão passa a
   ser uma tela configurável independente, apontando pra um evento específico
   ou pra um placar (geral ou customizado).
6. **Telão mostra top N fixo, não navega/pagina** — é uma tela grande sem
   interação humana; o admin configura quantas posições aparecem (top 3, 10,
   20...), sem rotação de páginas. Quando um novo score chega, aparece
   brevemente substituindo a última posição visível, some depois de alguns
   segundos.
7. **Ranking público (`ranking.html`) é a tela navegável** — precisa de
   paginação de verdade (é onde as pessoas procuram seu próprio placar) e de
   um campo de busca (por nick, nome ou pontuação).
8. **Paginação real na moderação do admin** — hoje só existe pela metade
   (feed busca lote fixo de 100, pendentes não pagina em nada).

---

## 2. Decisões fechadas

| # | Tópico | Decisão |
|---|---|---|
| 1 | Janela de envio (`data_inicio`/`data_fim`) | **Obrigatória** na criação do evento — todo evento nasce com início e fim definidos |
| 2 | Placares customizados | Entidade nomeada e persistida no admin (não filtro dinâmico ad-hoc) |
| 3 | Endpoint de upload genérico (`POST /api/upload`) | **Removido** — todo envio passa a exigir o slug do evento na URL |
| 4 | Jogos exibidos num telão de placar (geral/customizado) | Cada telão escolhe seus próprios jogos e ordem — independente de `evento_jogos` |
| 5 | Paginação do ranking público | Paginação real (20 por página) + campo de busca (nick, nome ou pontuação) — é a tela que as pessoas navegam pra achar seu placar |
| 6 | Exibição do telão | **Não pagina, não navega.** Top N fixo (admin configura N: 3, 10, 20...). Novo score chegando via SSE aparece por 5 segundos substituindo a última posição visível, depois some (volta ao top N real) |
| 7 | Paginação do admin (feed/pendentes) | Necessária de verdade — hoje só existe pela metade (feed busca lote fixo de 100, pendentes não pagina em nada) |

---

## 3. Modelo de dados

### `eventos` — três dimensões independentes (revisão de significado)

| Campo | Significado | Controla |
|---|---|---|
| `ativo` | Evento existe (não foi arquivado) | Aparece em listagens administrativas |
| `publico` | Visível publicamente | Ranking/telão acessíveis via `GET` — **inalterado**, já existe |
| `data_inicio` / `data_fim` | Janela de envio — **agora obrigatórios, ambos `NOT NULL`** | Aceita `POST` de novos scores |

Nenhuma mudança nos endpoints de leitura (`_get_evento_publico` continua
checando só `ativo` + `publico`, como hoje). A janela de datas só é checada
no momento do upload — um evento pode ficar `publico=true` para sempre,
mesmo com `data_fim` no passado: visível e consultável, só não aceita mais
envio.

**Migração necessária:** os 2 eventos existentes (`canal3expo`, `Evento
Padrão`) não têm `data_fim` hoje. Proposta de migração: para eventos sem
`data_fim`, preencher com `now() + interval '10 years'` (um valor
propositalmente distante — sinaliza "sem previsão de encerramento" sem
precisar de `NULL` especial no schema). Vou descrever o comportamento exato
antes de rodar, como sempre.

### `placares` (nova tabela)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `nome` | text | ex: "Hall da Fama Geral", "Temporada 2026" |
| `slug` | text UNIQUE | URL pública: `/api/p/{slug}/ranking/{jogo_slug}` |
| `escopo` | text | `'global'` \| `'customizado'` |
| `criado_em` | timestamptz | |

Um único placar `escopo='global'` é seedado por migração (slug `geral`) —
inclui todos os eventos, presentes e futuros, sem precisar de linha em
`placar_eventos` (é a query sem filtro de `evento_id`, o que
`listar_ranking` já faz hoje sem essa intenção estar explícita).

### `placar_eventos` (nova tabela — só para `escopo='customizado'`)

| Campo | Tipo | Notas |
|---|---|---|
| `placar_id` | FK → placares | |
| `evento_id` | FK → eventos | |

`UNIQUE(placar_id, evento_id)`. Membership curada manualmente pelo admin —
eventos novos não entram automaticamente num placar customizado.

### `teloes` (nova tabela)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `nome` | text | ex: "Telão Entrada Principal", "Telão Hall da Fama" |
| `slug` | text UNIQUE | URL pública: `/telao/{slug}` no frontend |
| `evento_id` | uuid FK nullable | telão de **um evento específico** |
| `placar_id` | uuid FK nullable | telão de um **placar** (geral ou customizado) |
| `top_n` | int `NOT NULL DEFAULT 10` | quantas posições ficam fixas na tela (ex.: 3, 10, 20) — **sem paginação, sem rotação de páginas** |
| `criado_em` | timestamptz | |

`CHECK ((evento_id IS NOT NULL) != (placar_id IS NOT NULL))` — um telão
aponta pra exatamente uma das duas coisas, nunca as duas nem nenhuma.

### `telao_jogos` (nova tabela)

| Campo | Tipo | Notas |
|---|---|---|
| `telao_id` | FK → teloes | |
| `jogo_id` | FK → jogos | |
| `ordem` | int | ordem no carrossel **daquele telão especificamente** |
| `ativo` | boolean `DEFAULT true` | permite remover um jogo do carrossel sem apagar a linha |

`UNIQUE(telao_id, jogo_id)`. Cada telão tem sua própria seleção e ordem de
jogos, **independente** de `evento_jogos` — mesmo um telão apontando pra um
`evento_id` específico não herda a ordem de `evento_jogos` automaticamente;
o admin configura por telão. (Decisão #4 — mais trabalho de configuração,
mais flexibilidade: dá pra um telão mostrar só 3 dos 5 jogos de um evento,
por exemplo.)

### `entradas.evento_id` → `NOT NULL`

Seguro de aplicar só depois do endpoint de upload genérico ser removido
(ponto 3) — não existe mais cenário de upload sem evento explícito na URL.

---

## 4. Fluxos

### 4.1 Upload (endpoint muda)

> ⚠️ **Nota de integração (com `AUTH_SPEC.md`):** a ordem completa abaixo
> já inclui as checagens de sessão/`nick_claims` do `AUTH_SPEC.md` §4.3 —
> os dois documentos descreviam esse mesmo endpoint de forma independente
> antes desta revisão. `AUTH_SPEC.md` §4.3 tem a versão detalhada da lógica
> de claim; aqui é só a posição dela na sequência de validações.

- `POST /api/upload` — **removido**.
- `POST /api/e/{slug}/upload` — único ponto de envio a partir de agora.
- Validações, em ordem:
  1. Evento existe? Não → `404`.
  2. Evento `publico=true`? Não → `403` (igual já funciona hoje).
  3. `now()` dentro de `[data_inicio, data_fim]`? Não → `422`, mensagem
     clara: "Este evento não está mais aceitando novas pontuações."
  4. Há sessão de auth válida (cookie)? → checa `nick_claims` (ver
     `AUTH_SPEC.md` §4.3): nick livre reivindica pro usuário logado, nick já
     seu segue, nick de outro usuário → `409`.
     Sem sessão → checa se o nick já está reivindicado por alguém; se
     estiver, `409` ("faça login pra usar esse nick"); se não, segue
     anônimo, exatamente como hoje.
  5. Segue o fluxo de upload já existente (validação de score, rate limit,
     foto, transação de superação), gravando `entradas.evento_id` sempre e
     `entradas.user_id` quando houver sessão.

`evento_repo.buscar_ativo_mais_recente` é removido — não faz mais sentido
com eventos simultâneos.

### 4.2 Ranking por placar

```
GET /api/p/{slug}/ranking/{jogo_slug}
```

Mesma lógica de `listar_ranking_por_evento`, mas:
- Se `placares.escopo = 'global'` → sem filtro de `evento_id` (todos).
- Se `placares.escopo = 'customizado'` → `evento_id IN (SELECT evento_id
  FROM placar_eventos WHERE placar_id = $1)`.

Desempate continua igual (`pontuacao DESC, criado_em ASC, id ASC`).

### 4.3 Telão

```
GET /telao/{slug}  (frontend)
GET /api/teloes/{slug}/config  (backend — nome, top_n, jogos ordenados)
```

O frontend usa a config pra saber: quantas posições mostrar fixas (`top_n`),
e por quais jogos girar o carrossel (via `telao_jogos`, ordenado). Pra cada
jogo, busca o ranking:
- Telão `evento_id` set → `/api/e/{evento_slug}/ranking/{jogo_slug}` (já existe).
- Telão `placar_id` set → `/api/p/{placar_slug}/ranking/{jogo_slug}` (novo, §4.2).

**Comportamento de novo score (SSE, já existe parcialmente hoje):** quando
chega um evento `novo_registro` pro jogo em exibição, a entrada nova aparece
imediatamente **substituindo a última posição visível** (posição `top_n`),
destacada, por **5 segundos fixos** — depois some e a tela volta a mostrar o
`top_n` real (se o score realmente entrou no top N, ele reaparece na posição
correta; se não entrou, some de fato). Isso é uma evolução do
`mostrarNovoRecorde` que já existe em `telao.html` hoje, só que a exibição
temporária passa a acontecer *dentro* da lista principal, não como banner
separado.

---

## 5. Paginação e busca

### Telão (`teloes` — sem paginação, tela fixa não navegável)
- Mostra sempre o `top_n` configurado (3, 10, 20...), sem páginas, sem
  rotação por tempo do ranking em si — é uma tela grande, ninguém interage
  com ela.
- Único elemento "temporário" é o destaque de novo score por 5 segundos
  (§4.3) — não é paginação, é um highlight passageiro.
- O carrossel que já existe hoje (trocar de **jogo** a cada X segundos)
  continua igual, isso não muda — o que não existe mais é paginar o
  **ranking dentro de um jogo**.

### Ranking público (`ranking.html` — navegável, com busca)
- Paginação real: **20 por página** (decisão #5 — sem configuração admin
  por agora), com controles "Anterior/Próxima" ou numerados.
- **Campo de busca**, filtrando por `nick`, `nome` ou `pontuação` — permite
  a pessoa achar sua entrada rapidamente sem precisar navegar página por
  página. Filtro client-side é suficiente para o volume esperado (dezenas a
  poucas centenas de entradas por jogo/evento); se crescer muito, migra pra
  busca no backend sem mudar a UX.

### Admin — feed e pendentes (moderação)
- `GET /api/admin/feed` já aceita `limit`/`offset` — só falta o **frontend**
  expor controles reais de paginação (hoje busca só `limit=100` fixo, sem
  ir além).
- `GET /api/admin/pendentes` **não tem paginação nenhuma hoje** — precisa
  ganhar `limit`/`offset` no repository e no router, igual ao feed.
- Ambos precisam de contagem total (`COUNT(*)`) pra o frontend saber quantas
  páginas existem — hoje nenhum dos dois retorna isso. Proposta: usar
  `COUNT(*) OVER()` na mesma query (evita um segundo round-trip ao banco).

---

## 6. Migração e compatibilidade

- `data_fim` obrigatório: migração precisa popular os eventos existentes
  antes de aplicar `NOT NULL` (ver §3).
- `entradas.evento_id NOT NULL`: já não há linhas `NULL` desde a Migration
  010 (todas foram associadas ao `canal3expo`) — aplicar a constraint é
  seguro.
- Placar `global` (slug `geral`) nasce por migração, sem precisar de ação
  do admin.
- **Telão atual = seed do "Hall da Fama Geral".** Conferi o `telao.html`
  hoje: ele já usa `/api/jogos` (todos os jogos ativos, ordenados por nome)
  e `/api/ranking/{slug}` (sem filtro de evento — ou seja, já é "geral" de
  fato, sem essa intenção estar explícita) com corte fixo de 10. A migração
  cria:
  - Uma linha em `teloes`: `nome='Hall da Fama Geral'`, `slug='geral'`,
    `placar_id` = o placar global, `top_n=10` (preserva o comportamento
    atual).
  - Linhas em `telao_jogos` para todos os jogos hoje `ativo=true`, na mesma
    ordem alfabética que `listar_ativos` já usa (`ORDER BY nome`) — ponto de
    partida idêntico ao que já existe; o admin reordena depois se quiser.
  - Isso não é migração de **dados de eventos**, é a criação da primeira
    linha em duas tabelas novas — sem risco pros dados existentes.
- `evento_repo.buscar_ativo_mais_recente` e o endpoint `POST /api/upload`
  saem juntos — checar se algo no frontend (`index.html`) ainda aponta pro
  endpoint antigo antes de remover.

---

## 7. Próximos passos

1. Migração SQL: `placares`, `placar_eventos`, `teloes`, `telao_jogos`,
   `eventos.data_fim NOT NULL`, `entradas.evento_id NOT NULL`.
2. Backend: novo router `/api/p/{slug}/...` (placares), novo router
   `/api/teloes/{slug}/config`, mover upload pra `/api/e/{slug}/upload`,
   adicionar paginação em `listar_pendentes`.
3. Admin: CRUD de placares, CRUD de telões (incluindo `telao_jogos`),
   controles de paginação real no feed/pendentes.
4. Frontend público: `ranking.html` ganha paginação (20/página) + campo de
   busca (nick/nome/pontuação); `telao.html` passa a ler config de
   `/api/teloes/{slug}/config` (top_n + jogos) em vez de assumir 1 evento
   fixo, e o destaque de novo score passa a substituir a última posição por
   5s em vez de só um banner.
5. Testes cobrindo: janela de envio (antes/depois/dentro), placar global vs.
   customizado, `CHECK` de telão (nem os dois nem nenhum de `evento_id`/
   `placar_id`), paginação de pendentes, comportamento de destaque de novo
   score no telão.
