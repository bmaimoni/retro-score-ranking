# Retro Score Ranking — Especificações do Projeto

> **Como usar este documento:** este é o ponto de partida para qualquer mudança no
> projeto. Antes de escrever código para uma nova especificação, ela deve ser
> discutida e registrada aqui primeiro — como uma seção nova, uma alteração em
> seção existente, ou uma entrada no backlog. Código é a implementação do que
> está descrito neste arquivo, não o contrário.
>
> Última sincronização com o código: commit `4f9f1a7` (2026-08-16).

---

## 1. Visão geral

**Retro Score Ranking** é um sistema de ranking ao vivo para eventos presenciais
de retrogaming (Canal3 High Score / Canal3 Expo). Visitantes fotografam a tela
do jogo com o placar visível, enviam a foto junto com nick e pontuação, e
aparecem imediatamente em um ranking público exibido em telão.

**Objetivo de produto:** criar competição e engajamento no evento físico, com
moderação leve (a ferramenta deve ser divertida e rápida de usar por visitantes
casuais, e simples de moderar por um humano em tempo real).

**Deploy ao vivo:** [retro-score-ranking.vercel.app](https://retro-score-ranking.vercel.app)

---

## 2. Stack técnica

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI (Python 3.12), `asyncpg` |
| Banco | PostgreSQL via Supabase |
| Storage de fotos | Supabase Object Storage |
| Frontend | HTML/CSS/JS vanilla (sem framework/build step) |
| Deploy backend | Railway |
| Deploy frontend | Vercel |
| Realtime | Server-Sent Events (SSE), implementado à mão (`services/sse.py`) |
| Logging | `structlog` (JSON estruturado) |

Sem ORM — todo acesso a dados é SQL cru via `asyncpg`, organizado em
`repositories/`.

---

## 3. Arquitetura de código

```
backend/
  main.py                 # bootstrap FastAPI, lifespan (pool de conexões), CORS
  config.py                # Settings via pydantic-settings (.env)
  middleware/auth.py       # require_admin — Bearer token, hmac.compare_digest
  routers/                 # camada HTTP (validação de entrada, orquestração)
    upload.py               # POST /api/upload — fluxo principal de participação
    ranking.py               # GET /api/ranking/*, SSE /api/events/ranking/{slug}
    jogos.py                  # GET /api/jogos, /api/jogos/config
    admin.py                   # moderação, gestão de jogos, config, manutenção
    eventos.py                   # CRUD de eventos (admin) — /api/admin/eventos
    evento_publico.py             # rotas públicas escopadas por evento — /api/e/{slug}
  services/                # regras de negócio puras (sem HTTP)
    nick.py                  # normalização de nick + "marcar superado"
    score.py                  # validação de pontuação vs score_max do jogo
    rate_limit.py             # decide se entrada vai para moderação
    storage.py                 # upload de foto pro Supabase Storage
    sse.py                      # broker pub/sub em memória para eventos ao vivo
  repositories/            # SQL cru, uma função por operação
    entrada.py, jogo.py, evento.py, evento_config.py, evento_jogo.py
  utils/
    db.py                     # pool asyncpg (get_pool/close_pool)
    ip.py                      # extração e hash (SHA-256 + salt) do IP do cliente
  migrations/               # SQL numerado sequencialmente, aplicado manualmente
                             # no Supabase SQL Editor (sem Alembic)
  tests/                    # pytest + pytest-asyncio + httpx (ASGITransport)
    smoke/                    # E2E com Playwright (fase C, precisa ambiente real)

frontend/
  index.html                # tela de upload (o visitante usa no celular)
  ranking.html               # ranking público de um jogo (scrollável, com histórico por nick)
  telao.html                  # exibição para o telão do evento (carrossel entre jogos, SSE)
  admin.html                   # painel de moderação (feed, pendentes, gestão de jogos/config)
  temas.js                      # temas visuais por slug de jogo (cores, tipografia, ícone)
  style.css                      # estilos compartilhados
```

**Padrão de camadas:** `router` (HTTP) → `service` (regra de negócio) →
`repository` (SQL). Routers não fazem SQL diretamente, exceto consultas
simples e específicas de uma única rota (ex.: joins de leitura em
`ranking.py`/`evento_publico.py` que não justificam um repository próprio).

---

## 4. Modelo de dados

### `jogos`
Catálogo de jogos disponíveis (global, não por evento).

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `nome` | text | |
| `slug` | text UNIQUE | usado em URLs (`/ranking/{slug}`) |
| `ativo` | boolean | jogos inativos somem dos seletores |
| `score_max` | integer nullable | `NULL` = sem limite; valida no upload |
| `criado_em` | timestamptz | |

### `entradas`
Cada tentativa/envio de score. É o histórico completo — nada é deletado por
padrão (soft delete via `arquivado`).

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `jogo_id` | uuid FK → jogos | `ON DELETE CASCADE` |
| `evento_id` | uuid FK → eventos, nullable | atribuído automaticamente no upload |
| `nick` | text | como digitado, para exibição |
| `nick_norm` | text | lowercase + trim + espaços colapsados, para comparação |
| `nome` | text nullable | nome/sobrenome real (opcional, migração 008) |
| `pontuacao` | integer | `CHECK (pontuacao > 0)` |
| `foto_url` | text nullable | **imutável — nunca é deletada**, mesmo se a entrada for oculta |
| `no_ranking` | boolean | `false` = oculta (moderação manual) |
| `superado` | boolean | `true` quando o mesmo nick envia um score novo no mesmo jogo |
| `pendente` | boolean | `true` = aguardando moderação (rate limit ou sem foto) |
| `arquivado` | boolean | soft delete via manutenção admin |
| `arquivado_em` / `arquivado_por` | | auditoria do soft delete |
| `ip_hash` | text | `SHA-256(ip + salt)` — nunca armazena IP em texto puro |
| `criado_em` | timestamptz | |
| `moderado_em` / `moderado_por` | | auditoria de moderação |

**Constraint crítica** — `nick_ativo_unico` (EXCLUDE USING gist): impede dois
registros simultaneamente "ativos" (`superado=false AND no_ranking=true AND
pendente=false AND arquivado=false`) com o mesmo `nick_norm` + `jogo_id`.
Aplicada no banco, não só na aplicação — protege contra race conditions em
envios concorrentes.

**Regra de negócio: superação por nick.** Ao inserir um novo score, a entrada
ativa anterior do mesmo `nick_norm` no mesmo jogo é marcada `superado=true`
**incondicionalmente** — mesmo que o novo score seja menor. Ou seja, cada nick
só pode ter uma entrada "valendo" por vez: a mais recente. (Ver §7 — decisão
consciente, não bug.)

**Regra de negócio: desempate de ranking.** Todas as queries de ranking
ordenam por `pontuacao DESC, criado_em ASC, id ASC`. Em empate de pontuação,
quem alcançou o score primeiro fica melhor posicionado. Isso é obrigatório —
sem desempate, o Postgres não garante ordem estável entre linhas empatadas, o
que já causou o bug de "score some do ranking" (corrigido no commit `7a3e77c`).

### `eventos`
Um evento físico (ex.: uma edição da Canal3 Expo).

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `nome` / `slug` | text | slug único, usado em `/api/e/{slug}/...` |
| `ativo` | boolean | eventos inativos não aparecem em `/ativos` |
| `publico` | boolean | `false` = telão/ranking desse evento ficam inacessíveis (override do admin), mesmo com o evento `ativo` |
| `logo_url` / `cor_primaria` | text nullable | identidade visual por evento |
| `data_inicio` / `data_fim` | timestamptz | |

### `evento_jogos` (N:N)
Vincula jogos a eventos, com ativação e ordem independentes por evento.

| Coluna | Tipo | Notas |
|---|---|---|
| `evento_id`, `jogo_id` | FK | `UNIQUE(evento_id, jogo_id)` |
| `ativo` | boolean | jogo pode estar desativado só nesse evento |
| `ordem` | int | ordem de exibição no evento |

Jogo com scores associados não pode ser removido da tabela `jogos`
(`ON DELETE RESTRICT` em `evento_jogos.jogo_id`).

### `evento_config`
Chave-valor genérico para textos e configurações da tela de upload (título,
subtítulo, texto de sucesso, texto LGPD, rate limit). Editável pelo admin sem
deploy.

---

## 5. Fluxos principais

### 5.1 Upload de score (`POST /api/upload`)
1. Valida foto (opcional): tipo por *magic bytes* (não pela extensão), máx 5MB.
   Aceita apenas JPEG/PNG.
2. Valida pontuação contra `score_max` do jogo (`services/score.py`).
3. Calcula `ip_hash` e checa rate limit (`services/rate_limit.py`) — limite e
   janela configuráveis via `evento_config`, com fallback pra env vars.
4. Se dentro do limite e com foto → `pendente=false` (aparece na hora).
   Se rate limit excedido **ou** sem foto → `pendente=true` (vai pra fila de
   moderação do admin).
5. Upload da foto pro Supabase Storage (se houver).
6. Busca evento ativo mais recente e associa à entrada.
7. Transação: marca entrada anterior do nick como `superado=true` + insere a
   nova.
8. Se não pendente, publica evento SSE `novo_registro` pros clientes do
   ranking/telão daquele jogo.

Conflito de `nick_ativo_unico` (dois envios simultâneos do mesmo nick) retorna
`409` com mensagem amigável, não `500`.

### 5.2 Moderação (admin)
- **Feed** (`GET /api/admin/feed`): todas as entradas recentes, incluindo
  ocultas/pendentes — paginado.
- **Pendentes** (`GET /api/admin/pendentes`): fila de decisão.
- **Ocultar/reativar** (`PATCH /api/admin/entradas/{id}`): alterna
  `no_ranking`. A foto nunca é deletada. Emite `ocultar`/`reativar` via SSE.
- **Resolver pendente** (`PATCH /api/admin/entradas/{id}/pendente`): aprova
  (`no_ranking=true`) ou rejeita (`no_ranking=false`) uma entrada da fila.
  Aprovação emite `novo_registro` via SSE.
- **Manutenção** (`POST /api/admin/manutencao/limpar-ranking` e
  `restaurar-ranking`): limpa um jogo específico ou todos, com soft delete
  (padrão, reversível) ou hard delete (`permanente=true`, irreversível).
  Exige `confirmar="CONFIRMAR"` no corpo — proteção contra clique acidental.

### 5.3 Ranking ao vivo (público)
- **Snapshot**: `GET /api/ranking/{slug}` — lista ordenada atual.
- **Líderes**: `GET /api/ranking/lideres` — top 1 de cada jogo ativo (usado
  nos cards do index). *(Rota registrada antes de `/{slug}` para não ser
  capturada pela rota genérica — ver §8.)*
- **Histórico por nick**: `GET /api/ranking/{slug}/historico/{nick}` — todas
  as tentativas do nick, mais recente primeiro, incluindo superadas/pendentes.
- **Stream**: `GET /api/events/ranking/{slug}` (SSE) — eventos
  `novo_registro`, `ocultar`, `reativar` em tempo real. Consumido por
  `ranking.html` e `telao.html`.

### 5.4 Multi-evento (público, escopado por slug)
Prefixo `/api/e/{slug}/...`, implementado em `evento_publico.py`:
- `GET /config` — nome, logo, cor primária do evento.
- `GET /jogos` — jogos ativos **naquele evento** (via `evento_jogos`).
- `GET /ranking/lideres` — top 1 por jogo, escopado ao evento.
- `GET /ranking/{jogo_slug}` — ranking escopado ao evento.

Acesso público checa: evento existe → `ativo=true` → `publico=true` (nessa
ordem; `publico=false` retorna `403`, evento inexistente ou inativo retorna
`404` — não vaza se o evento existe mas está desativado).

---

## 6. Segurança

- **RLS habilitado** em todas as tabelas públicas (`entradas`, `jogos`,
  `eventos`, `evento_config`, `evento_jogos`, e desde a migration 011/014
  também `placares`, `placar_eventos`, `teloes`, `telao_jogos`). O acesso do
  `app_user` é liberado por uma policy `app_user_all` (`PERMISSIVE`,
  `FOR ALL`, `USING true`, `WITH CHECK true`) em cada tabela — **não** por
  `BYPASSRLS` no role. Toda tabela nova com RLS precisa dessa policy
  explicitamente (ver armadilha em §8) — sem ela, o `app_user` não gera
  erro nenhum, só enxerga zero linhas silenciosamente.
- **`app_user`** dedicado no Postgres com permissões mínimas
  (SELECT/INSERT/UPDATE em geral + DELETE só em `entradas`), substituindo o
  usuário `postgres` (superuser) na `DATABASE_URL` do Railway.
- **IP nunca em texto puro**: sempre `SHA-256(ip + IP_HASH_SALT)`.
- **Admin**: token único via `ADMIN_SECRET`, comparado com
  `hmac.compare_digest` (evita timing attack). Sem múltiplos usuários/roles
  ainda (ver backlog — login/registro).
- **Validação de arquivo**: tipo verificado pelos *magic bytes* do conteúdo,
  não pela extensão ou `Content-Type` declarado pelo cliente.
- **Sem credenciais no histórico do git** (confirmado — só placeholders em
  `.env.example`).

---

## 7. Decisões de UX e produto já tomadas

Registradas aqui para não serem re-discutidas/revertidas sem querer:

- **Sem contagem total de participantes** no ranking público — evita
  desmotivar quem está mal posicionado.
- **Câmera vs. galeria**: no iOS, priorizar prompt de câmera é melhor UX que
  abrir a galeria direto.
- **Nick e nome em uppercase** nos campos de exibição.
- **Superação incondicional por nick**: um novo envio do mesmo nick sempre
  substitui o anterior como "ativo", mesmo que a pontuação seja menor —
  reflete a tentativa mais recente, não a melhor histórica. (Se isso mudar,
  precisa de decisão explícita — impacta `services/nick.py` e a constraint
  `nick_ativo_unico`.)
- **Desempate por ordem de chegada**: "quem alcançou a pontuação primeiro fica
  na frente" em caso de empate exato.
- **Evento desativado continua público por padrão**: `ativo=false` não
  esconde o telão/ranking automaticamente — isso é controlado à parte por
  `publico` (override manual do admin). Decisão tomada durante o design
  multi-evento (§8, Migration 010).
- **Scores órfãos** (sem `evento_id`, de antes da migração 009/010) foram
  todos associados ao evento `canal3expo`.

---

## 8. Estado atual do multi-evento

> ⚠️ **Este desenho está sendo substituído.** `docs/EVENTOS_SPEC.md` revisa
> tudo abaixo — eventos simultâneos, janela de envio separada de
> visibilidade, `placares` (geral + customizados) e `teloes` como entidade
> própria. Esta seção continua descrevendo o que **já está em produção**
> (Migration 010); consulte `EVENTOS_SPEC.md` para o que vem a seguir.

Migration 010 (aplicada) trouxe: `evento_jogos` (N:N), campos visuais em
`eventos` (`logo_url`, `cor_primaria`, `publico`), e migração de scores
órfãos.

5 decisões arquiteturais já validadas:
1. Desativar um evento **não** esconde telão/ranking por padrão — precisa do
   flag `publico=false` explícito.
2. Admins de evento poderão propor jogos para o catálogo global (ainda não
   implementado — backlog).
3. Ranking geral cross-event fica **deferido até existir login/registro de
   usuário** (sem isso não há como atribuir/mesclar identidade entre
   eventos).
4. Um único `admin.html` com dropdown de seleção de evento (painel de admin
   ainda não fatorado assim — hoje modera globalmente, sem filtro por
   evento).
5. Scores órfãos → `canal3expo`.

**Armadilha de ordenação de rotas FastAPI**: em qualquer router que tenha uma
rota `/{slug}/algo/{param}` e outra `/{slug}/algo/palavra-fixa`, a rota fixa
**precisa ser registrada antes** da rota com parâmetro dinâmico, ou o FastAPI
a captura como se fosse o parâmetro. Já causou um bug real (`/lideres` em
`evento_publico.py` ficou inacessível — corrigido no commit `7a3e77c`).
Manter esse cuidado em qualquer rota nova desse padrão.

**Armadilha de RLS em tabela nova**: `entradas`, `jogos`, `eventos`,
`evento_config` e `evento_jogos` têm RLS habilitado **e uma policy**
`app_user_all` (`PERMISSIVE`, `FOR ALL`, `USING true`, `WITH CHECK true`)
criada manualmente no Supabase — nunca documentada em nenhuma migration
até a `014`. `app_user` **não** tem `BYPASSRLS`. Toda tabela nova que
habilita RLS (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`) precisa da
mesma policy explicitamente, ou todo `SELECT`/`INSERT`/`UPDATE` do
`app_user` falha **silenciosamente** (zero linhas, sem erro nenhum) — foi
exatamente o que aconteceu com `placares`/`placar_eventos`/`teloes`/
`telao_jogos` na migration 011, só corrigido na `014`. Checklist pra
qualquer migration nova que crie tabela com RLS: sempre incluir
`CREATE POLICY app_user_all ON <tabela> FOR ALL TO app_user USING (true)
WITH CHECK (true);` (ou uma policy mais restrita, se fizer sentido pro
caso).

---

## 9. Testes

- `pytest` + `pytest-asyncio` + `httpx.AsyncClient` (via `ASGITransport`, sem
  subir servidor real).
- `FakePool`/`fake_pool` (em `conftest.py`) simula `asyncpg.Pool` para testes
  unitários de repository sem banco real.
- Testes de router usam `app.dependency_overrides[get_pool]` + `patch()` nos
  repositories/services.
- **Regra estabelecida**: toda feature de backend nova ganha pelo menos um
  teste antes do commit.
- Fases (`Makefile`):
  - `make unit` — unitários (mockado, roda em qualquer lugar)
  - `make integration` — subset dos unitários cobrindo fluxos completos
  - `make smoke` — E2E via Playwright, precisa de ambiente real (Supabase +
    Railway) — não roda em sandbox
- Rodar localmente/sandbox sem banco real exige env vars dummy:
  ```
  DATABASE_URL=x SUPABASE_URL=x SUPABASE_SERVICE_KEY=x ADMIN_SECRET=x IP_HASH_SALT=x \
    python3 -m pytest tests/ -q --ignore=tests/smoke
  ```
  (as 8 falhas que aparecem são de testes que tentam conectar a um Postgres
  real — esperado, não indicam regressão)

---

## 10. Backlog — pendências conhecidas

> Duas frentes grandes já saíram do estágio de ideia e viraram
> especificação fechada, ainda sem código: `docs/AUTH_SPEC.md`
> (autenticação/identidade) e `docs/EVENTOS_SPEC.md` (eventos simultâneos,
> placares, telões, paginação/busca). Os dois se cruzam no endpoint de
> upload (ver nota de integração em ambos, §4).
>
> **Ordem de implementação recomendada:** `EVENTOS_SPEC.md` primeiro. É a
> mudança mais estrutural no schema de `entradas` (`evento_id NOT NULL`,
> endpoint de upload movido pra `/api/e/{slug}/upload`) e não depende de
> autenticação existir. `AUTH_SPEC.md` entra depois, camada em cima do
> endpoint já estabilizado — adiciona `Depends(sessao_opcional)` e a
> checagem de `nick_claims` sem precisar mexer de novo na parte de eventos.

Em ordem aproximada de prioridade discutida:

- [ ] **Confirmar backup do Supabase** (pendente no dashboard).
- [ ] **Aplicar identidade visual 2026**: novo logo + paleta de cores (ambos
      já disponíveis no Google Drive — IDs de arquivo registrados na memória
      de conversas anteriores). Envolve `frontend/temas.js`, `style.css`, e
      possivelmente `logo_url`/`cor_primaria` na tabela `eventos`.
- [ ] **Implementar `EVENTOS_SPEC.md`** — eventos simultâneos, janela de
      envio, `placares`, `teloes`, paginação/busca no ranking. Ver §7 do
      próprio documento para a lista detalhada de passos.
- [ ] **Implementar `AUTH_SPEC.md`** — login opcional (Google + Magic Link),
      nick por claim, base para futuros apps Canal3. Depende do item
      anterior estar concluído no endpoint de upload (ver nota de
      integração em `AUTH_SPEC.md` §4.3). Ver §10 do próprio documento para
      a lista detalhada de passos.
- [ ] **Fluxo de admin de evento propondo jogos ao catálogo global** — ideia
      original do §8 desta seção, ainda não redesenhada à luz do
      `EVENTOS_SPEC.md` (hoje jogos são globais + vínculo por evento via
      `evento_jogos`; "propor" um jogo novo pro catálogo é fluxo de admin
      que ainda não foi especificado em detalhe).

**Superadas pelos documentos novos** (mantidas aqui só como histórico —
não são mais itens de backlog independentes):
- ~~`admin.html` unificado com seletor de evento~~ → `EVENTOS_SPEC.md` já
  prevê CRUD de placares/telões no admin; o desenho específico do seletor
  fica para a implementação.
- ~~Sistema de login/registro de usuário~~ → `AUTH_SPEC.md`.
- ~~Ranking geral cross-event~~ → `placares` (`escopo='global'`) em
  `EVENTOS_SPEC.md`.
- ~~Flag de override para telão pós-evento~~ → janela `data_inicio`/
  `data_fim` independente de `publico`, em `EVENTOS_SPEC.md` §3.

---

## 11. Convenções de trabalho

- **Migrações**: sempre descrever o comportamento (o que muda, é reversível?,
  afeta dados existentes?) antes de rodar qualquer SQL de migração — não
  rodar direto.
- **Testes antes do commit**: toda feature nova de backend leva teste. Bugs
  corrigidos idealmente ganham teste de regressão (ver `test_ranking_desempate.py`
  como padrão de referência).
- **f-strings vs. `str_replace`**: substituição de string Python em conteúdo
  HTML/JS tende a escapar crases (`` ` ``) incorretamente — preferir edição
  direta de arquivo a montar HTML via f-string quando o conteúdo tiver
  template literals JS.
- **`asyncpg`**: placeholders posicionais (`$1, $2...`), não nomeados. Chaves
  duplicadas em dict de parâmetros passam validação do Python silenciosamente
  e quebram a query em runtime — checar com atenção.
- **Módulos JS**: funções chamadas via `onclick` inline em HTML gerado
  dinamicamente precisam ser expostas como `window.nomeDaFuncao` dentro de
  `<script type="module">` (senão o escopo do módulo as esconde do HTML).
- **Canvas + fonte pixelada**: `document.fonts.load()` precisa ser aguardado
  antes de `canvas.measureText()` para métricas corretas com a fonte
  "Press Start 2P" (usada no telão/certificados, se aplicável).

---

## 12. Como propor uma nova especificação

Ao trazer uma ideia nova para o projeto:

1. Descreva o problema/necessidade primeiro, não a solução técnica.
2. Nós iteramos aqui neste documento: qual seção muda, o que entra em §7
   (decisão de produto) vs. §10 (backlog) vs. mudança em §4/§5 (schema/fluxo).
3. Só depois desse acordo entramos em migração, código e testes.

Isso mantém o `SPEC.md` como fonte da verdade — se o código e este documento
divergirem no futuro, é sinal de que uma mudança foi feita sem passar por
aqui, e o documento deve ser atualizado para refletir a realidade antes de
seguir adiante.
