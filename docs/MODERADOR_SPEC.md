# Moderador: escopo real vs. desenhado, e correção de autorização

> Status: **Fase 1 de 3 fechada e corrigida** (M.1-M.4 implementados,
> testados, sem regressão — ver §6) de uma revisão completa dos três
> níveis (moderador → admin de Arena → super), pedida pelo Bruno pra
> mapear com calma tudo que cada papel já faz hoje antes de separar
> `admin.html` em `console.html` (admin de Arena/moderador) e `admin.html`
> (exclusivo do super) — ver `docs/PAINEIS_ADMIN_SPEC.md` pro desenho de
> tela, ainda não iniciado. Este documento é sobre **o que o moderador
> pode fazer e por quê**, não sobre onde o botão fica.
>
> Nasceu de uma auditoria, não de uma ideia nova — `PERMISSOES_SPEC.md`
> §4 já fechou o desenho ("moderador só modera feed"); o que faltava era
> confirmar se a implementação bate com isso. Não bate: apareceram 3
> brechas de autorização, duas delas graves o bastante pra afetar a
> plataforma inteira, não só a Arena do moderador.

---

## 1. O que o moderador deveria poder fazer (desenho já fechado)

Ver `PERMISSOES_SPEC.md` §4 — única linha que libera moderador: **"Moderar
feed: ✅"**. Tudo mais (criar/editar jogo, evento, telão, conceder/revogar
vínculo, criar Arena) é `❌`. Escopo sempre por vínculo — uma pessoa é
moderador só nas Arenas onde tem esse vínculo ativo, nunca globalmente.

---

## 2. O que ele realmente consegue fazer hoje (auditoria)

| # | Endpoint | Escopo aplicado no backend | Visível/ativo no frontend hoje |
|---|---|---|---|
| 1 | `GET /api/admin/feed` | ✅ Correto — `event_id` obrigatório pra não-super, checa `tem_acesso_event` | Aba Feed, sempre visível |
| 2 | `PATCH /api/admin/entries/{id}` (ocultar/reativar) | 🔴 **Nenhum** — só autenticação, não checa se o evento da entry é de uma Arena onde o moderador tem vínculo | Ativo, é o botão principal do feed |
| 3 | `PATCH /api/admin/entries/{id}/pendente` (aprovar/rejeitar) | 🔴 **Nenhum**, mesmo problema | Ativo, fila de pendentes do feed |
| 4 | `GET /api/admin/games-todos` (leitura do catálogo) | Nenhum, mas catálogo é global por desenho (`SPEC.md`) — baixo risco | Aba Games, carregada automaticamente no login (`carregarTudo()`), mesmo sem clicar na aba |
| 5 | `PATCH /api/admin/games/{id}` (editar/ativar/desativar) | Bloqueia nível moderador (`admin.py:395`), mas não checa arena pra admin comum — acompanha o achado 1 do `PAINEIS_ADMIN_SPEC.md` | Botão de toggle escondido corretamente pro moderador (`ehAdminEmAlgumaMarca()`) — só afeta admin comum, não moderador |
| 6 | `GET /api/admin/config` + `PATCH /api/admin/config/{chave}` | 🔴 **Nenhum — nem checa `super`** | 🔴 **Seção "Configurações gerais" renderizada sem nenhum gate, dentro da aba Event, carregada automaticamente no login pra qualquer admin logado (`carregarTudo()` → `carregarConfig()`), sem precisar clicar em nada** |
| 7 | `GET /api/admin/usuarios/{id}/nicks` | Nenhum — qualquer admin vê histórico de nick de qualquer usuário da plataforma | — |
| 8 | `POST /api/admin/usuarios/{id}/trocar-nick` | Nenhum — por desenho parece intencional pra moderador (docstring: "Admin/moderador troca o nick de qualquer jogador"), mas alcance é a plataforma inteira, não só quem jogou na Arena do moderador | — |
| 9 | Manutenção (`limpar-ranking`, `restaurar-ranking`) | ✅ Correto — `_exigir_super_manutencao` | Cartões escondidos corretamente pra não-super (`manut-por-game`, `manut-geral`) |
| 10 | Games pendentes/aprovar/mesclar, Exclusões | ✅ Correto — super-only | Escondido corretamente |
| 11 | Criar jogo (`POST /games`) | ✅ Correto — exige nível `admin` | Formulário escondido corretamente pro moderador |

**Achado 6 é o mais grave**: `event_config` é uma tabela **legada,
singleton, sem `event_id`** (pré multi-evento) — guarda `evento_ativo`
(kill-switch de upload da plataforma inteira), `rate_limit`/
`rate_window_horas` (anti-abuso da plataforma inteira) e `lgpd_texto`
(texto de consentimento legal). Hoje, **qualquer moderador de qualquer
Arena consegue desligar upload pra todo mundo, afrouxar o rate limit
anti-spam, ou alterar o texto de consentimento LGPD** — sem nem precisar
procurar, porque a tela já carrega isso sozinha no login.

Achados 2 e 3 são os que atingem a razão de existir do papel: a única
coisa que moderador deveria poder fazer ("moderar feed") hoje **vaza pra
qualquer Arena da plataforma**, não só a dele — inclui publicação SSE ao
vivo pro telão de outra Arena.

---

## 3. Decisões propostas

| # | Tópico | Proposta |
|---|---|---|
| M.1 | Escopar `PATCH /entries/{id}` e `PATCH /entries/{id}/pendente` | Resolver `entry.event_id → events.arena_id` e checar `admin.tem_acesso_na_arena(arena_id)` antes de mutar — mesmo padrão já usado em `events.py`/`teloes_admin.py`. Super continua irrestrito. Exige teste adversarial explícito (moderador de Arena A tentando moderar entry de Arena B → 403) |
| M.2 | `event_config` (achado 6) | Travar pra **só super** (mesma régua de `_exigir_super_manutencao` — é config de plataforma, não de Arena). Frontend: mover a seção "Configurações gerais" pra fora de `console.html`, junto com o resto do que só super vê (`docs/PAINEIS_ADMIN_SPEC.md` II.2) |
| M.3 | Alcance de `trocar-nick`/`historico-nicks` | **Fechado — mantém global por agora.** Nick é identidade da pessoa na plataforma (`NICKNAME_SPEC.md`), não por Arena. **Trava permanente registrada pelo Bruno**: isso nunca pode virar porta pra enumeração de usuário — a plataforma não pode, agora nem no futuro, ter endpoint que liste todos os usuários ou permita descobrir/iterar contas sem já conhecer o `user_id` específico. Confirmado hoje: não existe `GET /api/admin/usuarios` nem nada parecido — os dois endpoints de M.3 exigem `user_id` já conhecido (só chegam a ele via feed, que após M.1 fica escopado à Arena do moderador). Qualquer endpoint futuro de busca/listagem de usuário (inclusive pra super) precisa respeitar essa trava — vale carregar esse princípio pra `ARENA_ADMIN_SPEC.md`/`SUPER_SPEC.md` quando chegar a vez |
| M.4 | Filtros/busca do feed (`BACKLOG_2026.md` §4.1/§4.4) | Já implementados e corretos (`status`, `data_de/data_ate`, `game_id`, `sem_foto`, `sem_identificacao`, `busca`) — sem mudança aqui, só confirmando que continuam funcionando depois de M.1 |

---

## 4. Riscos identificados

1. **M.1 precisa de teste adversarial antes de ser considerado pronto** —
   mesma exigência já registrada em `PERMISSOES_SPEC.md` §5.1 e
   `PAINEIS_ADMIN_SPEC.md` risco 2: checagem de escopo é a única linha de
   defesa, então tem que ser testada com moderador de uma Arena tentando
   agir sobre entry de outra, não só caminho feliz.
2. **M.2 muda comportamento hoje ativo em produção** — se algum admin de
   Arena (não super) estiver de fato usando a seção "Configurações
   gerais" pra algo (mesmo sem deveria), a mudança quebra esse uso.
   Precisa confirmar com o Bruno se alguém fora do super já mexeu nisso
   antes de travar (auditoria de log, se houver, ou simplesmente
   perguntar — não há histórico de quem editou `event_config`
   hoje, achado à parte: essa tabela não tem coluna de auditoria alguma,
   diferente de `admin_vinculos_auditoria`).

---

## 5. Fora de escopo desta rodada

Repensar o modelo de `event_config` pra virar per-evento de verdade
(hoje é singleton por decisão histórica, pré multi-evento) — a correção
aqui é só de **quem pode tocar nele**, não do modelo de dados. Fica
registrado como pendência arquitetural separada, sem fase própria ainda.

---

## 6. Implementação (concluída)

- [x] **M.1** — `_resolver_entry_com_acesso_ou_erro` (`routers/admin.py`)
  resolve `entry.event_id → events.arena_id` e checa
  `admin.tem_acesso_na_arena`, chamado no início de `moderar_entry` e de
  `resolver_pendente`. Super continua irrestrito; entry sem `event_id`
  (legado) bloqueada pra qualquer não-super. Testes adversariais em
  `tests/test_admin.py`: moderador de arena A bloqueado em entry da arena
  B (`entries/{id}` e `.../pendente`), moderador da própria arena
  funciona, entry sem `event_id` bloqueia não-super.
- [x] **M.2** — `_exigir_super_config` trava `GET/PATCH /api/admin/config`
  pra super. Frontend: seção "Configurações gerais" (`admin.html`)
  escondida via `aplicarVisibilidadePorNivel()` pra quem não é super, e
  `carregarTudo()` parou de buscar `/config` automaticamente pra
  não-super (evita 403 silencioso no polling). Testes: moderador e
  admin de arena recebem 403 em `GET`/`PATCH /config`.
- [x] Suíte completa rodada antes e depois — 662 passed (baseline
  conhecido: 18 smoke exigem browser/servidor, inalterado).
- [ ] M.4 (filtros/busca do feed) — sem mudança, já correto; confirmado
  na auditoria, sem item de implementação.
