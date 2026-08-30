# Admin de Arena: escopo real vs. desenhado, e correção de autorização

> Status: **Fase 2 de 3 fechada e corrigida** (AA.1-AA.3 implementados,
> testados, sem regressão — ver §6); a reconstrução de UI (jogos por
> evento, logo real) fica
> pra quando `docs/PAINEIS_ADMIN_SPEC.md` (separação `console.html`/
> `admin.html`) for implementado, depois da Fase 3 (super)**. Mesmo
> processo do `docs/MODERADOR_SPEC.md`: auditoria completa antes de
> desenhar tela.
>
> **Revisa `PERMISSOES_SPEC.md` §4**, linha "Criar/editar jogos... (própria
> marca): ✅ admin" — aquela decisão é de antes da IGDB (`CATALOGO_JOGOS_SPEC.md`
> Fase 5) tornar `games` um catálogo verdadeiramente global e
> compartilhado entre todas as Arenas. Editar o registro global de um
> jogo hoje não é mais "editar o jogo da minha marca" — é editar um
> recurso compartilhado. Ver AA.2.

---

## 1. O que o admin de Arena deveria poder fazer (desenho já fechado)

Ver `PERMISSOES_SPEC.md` §4 (revisado por `ARENA_SPEC.md` no mecanismo de
concessão, não nas regras) — admin comum: modera feed, cria/edita
events/telão da própria Arena, concede vínculo admin/moderador na própria
Arena, revoga vínculo de moderador. **Admin dono**, adicionalmente:
revoga vínculo de outro admin, transfere titularidade. Nunca: cria Arena
nova (isso agora é self-serve, `ARENA_SPEC.md` D.2 — qualquer usuário
autenticado vira admin ao criar a própria Arena), concede/revoga fora da
própria Arena.

---

## 2. Auditoria — o que ele realmente consegue fazer hoje

Varredura completa de `arenas_admin.py`, `events.py`, `teloes_admin.py`,
`memberships.py`, mais os endpoints de `games` em `admin.py` que também
afetam este papel.

| # | Área | Resultado |
|---|---|---|
| 1 | `arenas_admin.py` — CRUD de Arena, titularidade, convites, parcerias | ✅ **Tudo corretamente escopado** — cada endpoint usa `_exigir_admin_na_arena`/`eh_admin_na_arena`/`tem_acesso_na_arena`, exceto o achado 2 abaixo |
| 2 | `GET /api/admin/arenas/{arena_id}/events` | 🔴 **Sem escopo nenhum** — `_=Depends(require_admin)`, nem usa o `admin` resolvido. Qualquer admin/moderador de qualquer Arena lista nome/slug/`ativo`/`publico` dos eventos de **qualquer outra** Arena, inclusive não-públicos. Mesma classe do vazamento já corrigido em `PERMISSOES_SPEC.md` §8.1 (`GET /marcas`), a lição não foi replicada aqui |
| 3 | `events.py` — CRUD de event, vínculo jogo↔event | ✅ **Tudo corretamente escopado**, incluindo o sub-recurso `/{event_id}/games` (já usa `_exigir_admin_na_arena` pra escrita, `tem_acesso_na_arena` pra leitura) — é o endpoint que `docs/PAINEIS_ADMIN_SPEC.md` Fase I já identificou como "existe e nunca é usado pelo frontend" |
| 4 | `teloes_admin.py` — CRUD de telão, vínculo jogo↔telão | ✅ **Tudo corretamente escopado** |
| 5 | `memberships.py` — conceder/revogar/listar vínculo | ✅ **Tudo corretamente escopado**, `_pode_conceder`/`_pode_revogar` implementam exatamente a tabela do `PERMISSOES_SPEC.md` §4 (admin comum vs. dono) |
| 6 | `PATCH /api/admin/games/{id}` (editar registro global do jogo) | 🔴 Já registrado em `PAINEIS_ADMIN_SPEC.md` achado 1 — bloqueia moderador mas não escopa por Arena: admin de Arena A edita/desativa jogo "pertencente" (na prática, só usado por) Arena B |
| 7 | `POST /api/admin/games` com `event_id` no body (vincular ao criar) | 🔴 **Novo achado** — checa só "sou admin em alguma Arena", nunca que o `event_id` recebido pertence a uma Arena onde tenho vínculo. Admin de Arena A vincula um jogo recém-criado a um evento de Arena B só sabendo o `event_id` (UUID não é segredo forte, mas é uma escrita cross-Arena sem checagem nenhuma) |
| 8 | Frontend — toggle "jogo ativo" no painel | 🟠 Já registrado em `PAINEIS_ADMIN_SPEC.md` (achado 1/Fase I) — usa o endpoint global errado em vez de `event_games`. Fica pra quando a UI for reconstruída (§4) |
| 9 | Frontend — logo da Arena | 🟠 Já registrado em `PAINEIS_ADMIN_SPEC.md` (achado 3/III.1) — texto, não upload real. Mesma situação |

---

## 3. Decisões

| # | Tópico | Decisão |
|---|---|---|
| AA.1 | `GET /{arena_id}/events` (achado 2) | Escopar com `tem_acesso_na_arena` (leitura liberada pra admin **e** moderador da Arena, mesmo padrão de `listar_games_do_event`) — hoje só é chamado pelo wizard (contexto já restrito à própria Arena no frontend), então o fix é puramente defesa em profundidade, sem mudar comportamento observável de ninguém usando o fluxo normal |
| AA.2 | `PATCH /games/{id}` (achado 6) — revisão de `PERMISSOES_SPEC.md` §4 | **Fechado: vira exclusivo de super.** `games` é catálogo global compartilhado (`CATALOGO_JOGOS_SPEC.md` Fase 5) — editar nome/capa/plataforma/`score_max`/`ativo` do registro afeta toda Arena que usa aquele jogo, não só a de quem editou. O que admin de Arena continua controlando de verdade é **o vínculo** (`event_games.ativo`/`ordem`) — já correto e escopado em `events.py`, só falta a UI (`PAINEIS_ADMIN_SPEC.md` Fase I) |
| AA.3 | `POST /games` com `event_id` (achado 7) | Antes de vincular, checar `admin.super or admin.tem_acesso_na_arena(event.arena_id)` — resolvendo a Arena do `event_id` recebido, mesmo padrão de `_exigir_admin_na_arena` já usado em `events.py`. Sem `event_id`, comportamento não muda (não vincula a nada) |
| AA.4 | Criar Arena nova | Sem mudança — já é self-serve por design (`ARENA_SPEC.md` D.2), fora do escopo de autorização "admin" (é `require_authenticated_user`, antes de existir qualquer vínculo) |

---

## 4. O que fica para a reconstrução de UI (fora desta rodada)

Já documentado em `docs/PAINEIS_ADMIN_SPEC.md` — não duplicado aqui:
- Fase I — trocar a aba "Games" do painel pra usar `event_games` (I.1-I.4), consequência direta de AA.2
- III.1 — logo real via upload
- Fase II — separação `console.html`/`admin.html`

Ordem combinada com o Bruno: fechar as 3 specs de papel (moderador ✅,
admin de Arena ✅, super — próxima) antes de iniciar a reconstrução de
UI, pra desenhar as telas já sabendo o que cada papel deveria ver, em vez
de redesenhar de novo depois.

---

## 5. Riscos identificados

1. **AA.2 muda comportamento hoje ativo.** Se algum admin de Arena não
   for super e já estiver usando o toggle "ativo"/editando `score_max`
   pela aba Games (mesmo que incorretamente, sobre o catálogo global),
   essa ação passa a dar 403. É a correção certa (a ação nunca deveria
   ter afetado o catálogo global), mas é uma mudança de comportamento
   observável — vale o Bruno saber que qualquer admin de Arena não-super
   usando esse toggle hoje vai notar a mudança até a UI de `event_games`
   existir (Fase I do `PAINEIS_ADMIN_SPEC.md`).
2. **AA.3 precisa de teste adversarial** — mesma exigência já repetida em
   `PERMISSOES_SPEC.md` §5.1, `PAINEIS_ADMIN_SPEC.md` e
   `MODERADOR_SPEC.md`: checagem de escopo é a única defesa, testa com
   admin de Arena A tentando vincular jogo a event de Arena B.

---

## 6. Implementação (concluída)

- [x] **AA.1** — `_exigir_acesso_na_arena` (nome local) em
  `GET /api/admin/arenas/{arena_id}/events`.
- [x] **AA.2** — `_exigir_super_editar_game` trava `PATCH /games/{id}`
  pra `admin.super`. Teste existente `test_atualizar_game_admin_escopado`
  atualizado pra refletir a decisão nova (era 200, passa a ser 403);
  teste antigo de moderador (`test_atualizar_game_moderador_retorna_403`)
  continua válido sem mudança.
- [x] **AA.3** — checagem de Arena do `event_id` antes de vincular em
  `POST /games`, reaproveitando `event_repo.buscar_por_id`.
- [x] Frontend: toggle "ativo" da aba Games escondido pra quem não é
  super (era `ehAdminEmAlgumaMarca()`, virou `meInfo.super`) — evita
  expor um controle que agora sempre dá 403 pra admin de arena, até a
  Fase I do `PAINEIS_ADMIN_SPEC.md` trocar pela UI de `event_games`.
- [x] Testes adversariais novos + suíte completa sem regressão (665
  passed).
