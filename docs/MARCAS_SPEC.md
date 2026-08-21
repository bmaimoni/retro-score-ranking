# Marcas, Identidade Visual e Navegação — Retro Score Ranking

> Status: **decisões fechadas, pronto para commit**. Complementa
> `EVENTOS_SPEC.md` — introduz um nível novo (`marcas`) acima de `eventos`,
> e revisita a navegação de `index.html`/`ranking.html`.

---

## 1. Objetivo

1. **Multi-marca**: hoje o projeto suporta múltiplos eventos simultâneos
   (`EVENTOS_SPEC.md`), mas identidade visual (`logo_url`, `cor_primaria`) só
   existe por evento individual, sem reaproveitamento. Uma marca pode ter
   vários eventos — todos devem herdar a mesma identidade visual por
   padrão, sem precisar configurar de novo em cada evento.
2. **Tipografia configurável**: hoje só a cor primária e o logo são
   configuráveis por evento; tipografia é fixa no CSS.
3. **Navegação em `index.html` com mais jogos**: busca por texto, e um jeito
   de pular a lista inteira quando a pessoa já sabe qual jogo quer (ver
   crítica ao índice alfabético em §2).
4. **Link direto pro ranking de um jogo específico**, respeitando o
   contexto de evento/marca da página — hoje só existe "ver ranking geral"
   (sempre o placar sem filtro de evento).

---

## 2. Decisões fechadas

| # | Tópico | Decisão |
|---|---|---|
| 1 | Relação marca ↔ evento | Marca é um nível **acima** de evento — uma marca tem vários eventos, todos herdando a identidade visual por padrão |
| 2 | Precedência de identidade visual | **Cor e tipografia**: `evento` (se setado) → `marca` vinculada (se setada) → default da plataforma. **Logo**: **não herda** — cada evento tem sempre o seu próprio logo; o logo da marca é usado só em contextos de marca inteira (ex.: um Hall da Fama que abrange vários eventos da mesma marca), nunca como fallback pro logo de um evento específico |
| 3 | Índice alfabético (A-Z) na lista de jogos | **Rejeitado por ora** — ver crítica em §2.1. Substituído por busca por texto + link direto por jogo (QR por cabine) |
| 4 | Tipografias oferecidas | 3 presets, reaproveitando fontes já carregadas (sem pedir mais requisições): `arcade` (Press Start 2P, padrão atual), `futurista` (Orbitron), `terminal` (Share Tech Mono) |
| 5 | `ranking.html` | Passa a aceitar `?evento=slug` (mesmo padrão já usado em `index.html`), escopando o ranking pro evento em vez do placar geral |
| 6 | Link "ver ranking" por jogo | Cada card de jogo em `index.html` ganha um link pro ranking daquele jogo específico, **antes** de submeter score, carregando o contexto de evento da página |
| 7 | Moderação/admin escopado | Administradores deixam de ser um token único compartilhado — cada um é uma conta (mesmo sistema de login do `AUTH_SPEC.md`) vinculada a **um evento**, **uma marca** (enxerga todos os eventos dela), ou **super-admin** (enxerga tudo) |

### 2.1 Crítica ao índice alfabético (respondendo à pergunta original)

Concordo com a busca por texto, mas tenho ressalva sobre o índice A-Z:

- **Selecionar jogo é reconhecimento visual, não recall textual.** A pessoa
  geralmente reconhece o jogo pela arte/nome de vista, não sabe de cabeça a
  grafia exata ("Pac-Man" vs "Pacman" vs "PAC MAN") — pensar em ordem
  alfabética exige uma memória que esse contexto não costuma ter.
- **Volume provável não justifica.** Eventos de arcade físico têm dezenas
  de cabines, não centenas — a faixa onde um índice A-Z compensa (listas de
  contatos, catálogos grandes) é bem maior que isso. Busca por texto simples
  já resolve dezenas de itens sem precisar de navegação auxiliar.
- **Ruim em mobile.** 26 letras como alvo de toque ficam minúsculas numa
  tela de celular, ou o índice em si vira difícil de usar.

**Alternativa proposta e aceita**: link direto por jogo (QR por cabine
física), que ataca o problema na raiz para o caso de uso mais comum
(pessoa já está na cabine, quer registrar o score daquele jogo específico)
— ela nem precisa navegar lista nenhuma. Busca cobre quem quer submeter um
jogo diferente do que está na frente. Se o número de jogos por evento
crescer muito no futuro, um agrupamento por categoria/gênero (Luta,
Corrida, Plataforma...) tende a ajudar mais que ordem alfabética — fica
registrado como ideia pra retomar se a necessidade aparecer, não implementado
agora.

---

## 3. Modelo de dados

### `marcas` (nova tabela)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `nome` | text | ex.: "Canal3" |
| `slug` | text UNIQUE | |
| `cor_primaria` | text nullable | hex; `NULL` = usa default da plataforma |
| `tipografia` | text nullable | um de `arcade`/`futurista`/`terminal`; `NULL` = default |
| `logo_url` | text nullable | |
| `criado_em` | timestamptz | |

### `eventos` — 2 campos novos

| Campo | Tipo | Notas |
|---|---|---|
| `marca_id` | uuid FK nullable → marcas | `ON DELETE SET NULL` — apagar a marca não apaga o evento, só desvincula |
| `tipografia` | text nullable | mesmo padrão de override que `logo_url`/`cor_primaria` já têm |

### Resolução de identidade visual (lógica de backend, não de frontend)

**Cor e tipografia** herdam da marca:
```
valor_resolvido = eventos.<campo>
                   OR (marca vinculada).<campo>
                   OR default da plataforma (frontend já sabe, não precisa vir da API)
```

**Logo não herda.** `eventos.logo_url` é sempre independente — cada evento
tem o seu. `marcas.logo_url` existe como atributo próprio da marca, usado
só em telas de contexto de marca inteira (ex.: um placar/telão que reúne
vários eventos da mesma marca — ver `EVENTOS_SPEC.md` §3, `placares`). Se
um evento não tiver `logo_url` setado, o frontend usa o logo default da
plataforma — **nunca** o da marca.

O backend resolve essa cadeia e devolve só o valor final em
`GET /api/e/{slug}/config` — o frontend não precisa saber de herança, só
aplica o que veio (ou usa seu próprio default se vier `null`).

---

## 4. Fluxos

### 4.1 Config do evento resolve a identidade herdada

`GET /api/e/{slug}/config` (endpoint já existe) passa a incluir
`tipografia` resolvida junto com `logo_url`/`cor_primaria`, já aplicando a
precedência do §3. Sem mudança de contrato pra quem só usava os 2 campos
que já existiam.

### 4.2 Busca de jogos em `index.html`

Filtro client-side sobre a lista já carregada (mesmo padrão já usado em
`ranking.html`), por `nome` do jogo. Sem mudança de backend.

### 4.3 Link direto por jogo (QR por cabine)

```
index.html?evento={slug}&jogo={jogoSlug}
```
Se `jogo` estiver presente na URL: mostra **só** o card daquele jogo, já
expandido, com um link discreto "Ver todos os jogos" pra revelar a lista
completa (caso a pessoa queira enviar outro score também). Sem esse
parâmetro, comportamento atual (lista completa) inalterado.

### 4.4 Link "ver ranking" por jogo

Cada card de jogo (na visão fechada, antes de expandir o formulário) ganha
um link "Ver ranking →", apontando para:
```
ranking.html?evento={EVENTO_SLUG}&jogo={jogoSlug}
```
Herdando o `EVENTO_SLUG` que a própria página já resolveu (parâmetro de URL
com fallback pro evento padrão, mesmo mecanismo já usado no upload).

### 4.5 `ranking.html` ganha contexto de evento

Hoje `ranking.html` sempre busca `/api/ranking/{slug}` (placar geral, sem
filtro). Passa a:
```
const EVENTO_SLUG = new URLSearchParams(location.search).get('evento');
```
Se presente → `GET /api/e/{EVENTO_SLUG}/ranking/{jogoSlug}`.
Se ausente → comportamento atual, inalterado (links/QRs já publicados sem
esse parâmetro continuam mostrando o placar geral, exatamente como hoje).

---

## 5. Frontend — aplicação da identidade visual

`index.html` (e candidatos futuros: `ranking.html`, `telao.html`) aplicam a
config resolvida via CSS custom properties, no carregamento:

```js
const TIPOGRAFIAS = {
  arcade:     "'Press Start 2P', 'Pixel Operator', monospace",
  futurista:  "'Orbitron', sans-serif",
  terminal:   "'Share Tech Mono', monospace",
};

function aplicarIdentidadeVisual(config) {
  if (config.cor_primaria) {
    document.documentElement.style.setProperty('--color-primary', config.cor_primaria);
  }
  if (config.tipografia && TIPOGRAFIAS[config.tipografia]) {
    document.documentElement.style.setProperty('--font-display', TIPOGRAFIAS[config.tipografia]);
  }
  if (config.logo_url) {
    document.querySelector('.page-logo').src = config.logo_url;
  }
}
```
As 3 fontes já são carregadas hoje via Google Fonts em `index.html` (linha
do `<link>` já inclui Press Start 2P, Orbitron e Share Tech Mono) — trocar
tipografia não pede requisição de rede nova.

---

## 6. Administração escopada por marca/evento

Hoje `middleware/auth.py:require_admin` checa um único `ADMIN_SECRET`
compartilhado por Bearer token — quem tem o token vê e modera **tudo**,
sem distinção. Isso deixa de fazer sentido com múltiplas marcas: um
administrador de uma marca não deveria conseguir moderar eventos de outra.

Isso também **reabre** uma decisão que `AUTH_SPEC.md` §6 tinha
propositalmente adiado ("RBAC/ABAC — autorização de admin já existe
separada, não precisa se fundir com identidade de visitante agora") — a
tabela de decisões adiadas daquele documento precisa ser atualizada pra
refletir isso quando este trabalho for implementado.

### Modelo de dados

```
admin_vinculos
  id          uuid PK
  user_id     uuid FK → users(id) ON DELETE CASCADE
  escopo      text CHECK (escopo IN ('super', 'marca', 'evento'))
  marca_id    uuid FK → marcas(id)  ON DELETE CASCADE, nullable
  evento_id   uuid FK → eventos(id) ON DELETE CASCADE, nullable
  criado_em   timestamptz
  CHECK (
    (escopo = 'super'  AND marca_id IS NULL     AND evento_id IS NULL) OR
    (escopo = 'marca'  AND marca_id IS NOT NULL AND evento_id IS NULL) OR
    (escopo = 'evento' AND evento_id IS NOT NULL AND marca_id IS NULL)
  )
```

Reaproveita `users` do `AUTH_SPEC.md` — um administrador **é** uma conta
comum, só que com um ou mais vínculos de admin. Uma pessoa pode acumular
vários vínculos (ex.: admin de 2 eventos específicos de marcas diferentes,
sem ser admin de nenhuma marca inteira).

### Regra de autorização

Para uma ação sobre um `evento_id` alvo, nessa ordem:
1. Usuário tem vínculo `escopo='super'`? → permite.
2. Usuário tem vínculo `escopo='marca'` cujo `marca_id` bate com a marca
   do evento-alvo? → permite.
3. Usuário tem vínculo `escopo='evento'` cujo `evento_id` bate com o
   evento-alvo? → permite.
4. Nenhum dos três → nega (403).

Ações não ligadas a um evento específico (criar marca nova, listar todas
as marcas, etc.) exigem `escopo='super'`.

### Transição do `ADMIN_SECRET`

Mantido como mecanismo de bootstrap/emergência (equivalente a super-admin)
— não removido. Evita o problema do ovo-e-galinha: precisa de alguém com
acesso de admin pra cadastrar o primeiro `admin_vinculo`. Login de admin
passa a aceitar **dois caminhos**: o Bearer token de sempre (super-admin,
sem mudança), **ou** uma sessão de visitante comum (`AUTH_SPEC.md`) cujo
usuário tenha um `admin_vinculo` compatível com a ação.

### Efeito colateral necessário: feed e pendentes precisam saber o evento

Hoje `GET /api/admin/feed` e `GET /api/admin/pendentes` (`EVENTOS_SPEC.md`
§5) listam entradas de **todos** os eventos, sem filtro algum — um admin
com escopo restrito a um evento específico não pode ver essa lista sem
vazar dados de eventos que não são dele. Os dois endpoints vão precisar
ganhar um filtro por `evento_id`, obrigatório (não opcional) pra quem não
for super-admin — detalhe de implementação a fechar quando essa fase for
codada, não bloqueia o desenho acima.

---

## 7. Migração e compatibilidade

- `marcas` nasce vazia — nenhum evento é obrigado a ter marca. Sem marca
  vinculada, tudo continua exatamente como hoje (evento usa seus próprios
  `logo_url`/`cor_primaria`, ou o default da plataforma).
- `eventos.marca_id` e `eventos.tipografia` nascem `NULL` em todas as linhas
  existentes — zero mudança de comportamento pros 2 eventos já cadastrados
  até alguém vincular uma marca ou setar tipografia manualmente.
- **Lição já aprendida (migrations 011-014, ver SPEC.md §8)**: `marcas` e
  `admin_vinculos` precisam nascer com RLS + policy `app_user_all` desde a
  própria migração, não depois — não repetir o bug do telão invisível.
- `ranking.html` sem `?evento=` continua mostrando o placar geral — nenhum
  QR/link já publicado quebra.
- `admin_vinculos` nasce vazia — `ADMIN_SECRET` continua funcionando
  sozinho até o primeiro vínculo real ser cadastrado (por alguém usando o
  próprio `ADMIN_SECRET` pra se auto-cadastrar como super-admin, resolvendo
  o ovo-e-galinha).

---

## 8. Próximos passos

1. Migração SQL: `marcas`, `eventos.marca_id`, `eventos.tipografia`,
   `admin_vinculos` — com RLS + policy desde o início.
2. Backend (identidade visual): `repositories/marca.py` +
   `routers/marcas_admin.py` (CRUD, mesmo padrão de
   `placares_admin.py`/`teloes_admin.py`); resolução de herança em
   `GET /api/e/{slug}/config`; `ranking.html`'s contraparte —
   `routers/evento_publico.py` já tem o endpoint de ranking por evento,
   só falta o frontend usar.
3. Backend (admin escopado): evoluir `middleware/auth.py:require_admin`
   pra aceitar sessão+vínculo além do Bearer token; filtro de `evento_id`
   obrigatório em feed/pendentes pra quem não for super-admin; endpoints de
   CRUD de `admin_vinculos` (só super-admin cria/remove vínculo de outra
   pessoa).
4. Frontend: busca em `index.html`; parâmetro `?jogo=` (link direto);
   `aplicarIdentidadeVisual()`; link "ver ranking" por card; `ranking.html`
   ganha `?evento=`.
5. Admin: CRUD de marcas, campo de vínculo marca↔evento no formulário de
   evento existente; UI pra super-admin gerenciar vínculos de outros
   administradores; `admin.html` migra de "só token" pra "login + vínculo"
   (login continua aceitando o token como atalho de super-admin).
6. Testes: resolução de herança (evento > marca > default, nas 3
   combinações, com logo sempre não-herdado), `?jogo=` mostrando card
   único, `ranking.html` com/sem `?evento=`, as 4 combinações de
   autorização escopada (super/marca/evento/nenhum) pra uma ação sobre um
   evento-alvo.

`AUTH_SPEC.md` §6 já foi atualizado nesta mesma sessão, marcando RBAC/ABAC
como reaberto aqui — não é mais um passo pendente.
