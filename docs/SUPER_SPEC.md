# Super: escopo real vs. desenhado, e correção de autorização

> Status: **Fase 3 de 3 fechada e corrigida** (S.1-S.2 implementados,
> testados, sem regressão — ver §6). Fecha a revisão completa dos três
> níveis (moderador → admin de Arena → super) pedida pelo Bruno antes de
> separar `admin.html` em `console.html` (admin de Arena/moderador) e
> `admin.html` (exclusivo do super) — ver `docs/PAINEIS_ADMIN_SPEC.md`
> pro desenho de tela, ainda não iniciado. Mesmo processo do
> `docs/MODERADOR_SPEC.md` e `docs/ARENA_ADMIN_SPEC.md`: auditoria
> completa antes de desenhar tela.
>
> Diferença de foco em relação às duas rodadas anteriores: lá o risco
> era "papel restrito consegue fazer mais do que deveria" (vazamento
> cross-arena). Aqui, como `super` é desenhado pra não ter restrição
> nenhuma, o risco é o oposto — **ações que deveriam ser exclusivas de
> super (ou escopadas por arena) e não são**, porque nasceram antes do
> pivô Arena multi-tenant e nunca foram revisadas.

---

## 1. O que super deveria poder fazer (desenho já fechado)

`PERMISSOES_SPEC.md` §4: `super` vê e administra tudo, sem checagem de
escopo — qualquer arena, criar arena (pré-pivô; hoje é self-serve,
`ARENA_SPEC.md` D.2, fora do escopo de autorização "admin"), conceder
vínculo `admin`/`moderador`/`super` em qualquer arena, revogar qualquer
vínculo, transferir titularidade de qualquer arena.

Poderes adicionais que nasceram fora desse documento, um por um conforme
a plataforma cresceu, nunca consolidados numa tabela só:

- Editar o catálogo global de games (`ARENA_ADMIN_SPEC.md` AA.2) —
  nome/capa/plataforma/`score_max`/ativo, porque `games` é
  compartilhado entre todas as Arenas desde a Fase 5 do
  `CATALOGO_JOGOS_SPEC.md` (IGDB).
- Revisar/aprovar/mesclar games pendentes de aprovação (migration 018).
- CRUD de avatares (galeria curada, `BACKLOG_2026.md` §1).
- Configuração de plataforma (`event_config`, tabela legada singleton).
- Manutenção de ranking (`limpar-ranking`/`restaurar-ranking`) — afeta
  todas as Arenas de uma vez.
- Processar exclusão de conta (LGPD, `EXCLUSAO_CONTA_SPEC.md`) —
  usuário não é escopado por arena.
- Ver a fila de arenas em `status='draft'` (`ARENA_SPEC.md` B.4).
- Mover um `event` entre Arenas.

---

## 2. Auditoria — o que ele realmente consegue fazer hoje

Varredura completa de todo uso de `admin.super`/`_exigir_super*` em
`admin.py`, `arenas_admin.py`, `avatares_admin.py`, `events.py`,
`memberships.py`, `teloes_admin.py`, mais a base (`middleware/auth.py`).

| # | Área | Resultado |
|---|---|---|
| 1 | Bootstrap via `Bearer <ADMIN_SECRET>` | ✅ Sempre `super=True`, comparação por `hmac.compare_digest` (sem timing leak) |
| 2 | `manutenção`, `config`, `exclusão de conta`, `games pendentes/aprovar/mesclar`, `avatares`, fila de arenas `draft`, transferência de titularidade, mover `event` entre Arenas | ✅ **Tudo corretamente exclusivo de super** — cada um com seu `_exigir_super_*` (ou checagem equivalente), super sempre irrestrito nas demais rotas |
| 3 | `PATCH /games/{id}` (catálogo global) | ✅ Já fechado em AA.2 — exclusivo de super |
| 4 | `GET /api/admin/usuarios/{user_id}/nicks` | 🔴 **Sem escopo nenhum** — só `require_admin`. Qualquer admin/moderador de qualquer Arena vê o histórico completo de nicks de **qualquer usuário da plataforma**, mesmo um que nunca jogou na própria Arena |
| 5 | `POST /api/admin/usuarios/{user_id}/trocar-nick` | 🔴 **Mesmo problema, mais grave** — qualquer admin/moderador força a troca de nick de qualquer usuário, ignorando o cooldown de 30 dias, sem nenhuma relação exigida com a própria Arena. `user_id` não é segredo (descobrível via `perfil.py` — seguir/seguidores/atividade, recursos cross-arena por design do pivô Arena), então é um vetor de assédio real, não só teórico |
| 6 | `GET /api/admin/games-todos` | 🟠 **Vaza games pendentes de outras Arenas** — sem checagem de `super`, retorna também `pendente_aprovacao=true` de qualquer Arena. Confirmado explorável pela própria UI: `admin.html` mostra o badge "Aguardando aprovação" na aba Games pra qualquer nível, não só super |
| 7 | `memberships.py` (conceder/revogar/listar, inclusive `scope='super'`) | ✅ Já auditado e correto em `ARENA_ADMIN_SPEC.md` §2 item 5 — sem achado novo aqui |

---

## 3. Decisões

| # | Tópico | Decisão |
|---|---|---|
| S.1 | Moderação de nick sem escopo (achados 4/5) | **Escopar por arena, não restringir a super.** Admin/moderador só pode ver histórico ou forçar troca de nick de um `user_id` que tenha ao menos 1 entry num event de uma Arena onde ele tem vínculo — mesmo padrão do M.1 pra entries (checagem de acesso antes de mutar, super sempre irrestrito). Não muda o fluxo normal: os botões já só aparecem no feed da própria Arena (já escopado desde M.1); o fix fecha o bypass de chamar a API direto com um `user_id` arbitrário descoberto por outro caminho (seguir/atividade) |
| S.2 | `games-todos` vazando pendentes de outras Arenas (achado 6) | **Esconder pendentes de quem não é super.** Não-super só vê games já aprovados na lista — inclusive os que ele mesmo submeteu, que continuam pendentes até a revisão do super. Simples, sem precisar checar autoria (`criado_por`); a aba "Games" está de qualquer forma marcada pra reconstrução (`PAINEIS_ADMIN_SPEC.md` Fase I) |

---

## 4. O que fica para a reconstrução de UI (fora desta rodada)

Já documentado em `docs/PAINEIS_ADMIN_SPEC.md` — não duplicado aqui:
- Fase I — trocar a aba "Games" do painel pra usar `event_games`
- III.1 — logo real via upload
- Fase II — separação `console.html`/`admin.html`

As 3 specs de papel estão fechadas agora (moderador ✅, admin de Arena
✅, super ✅) — próximo passo combinado com o Bruno é a reconstrução de
UI do `PAINEIS_ADMIN_SPEC.md`, já sabendo o que cada papel deveria ver.

---

## 5. Riscos identificados

1. **S.1 muda comportamento hoje ativo, em tese.** Um admin/moderador
   que hoje force a troca de nick de alguém fora da própria Arena
   (comportamento que nunca deveria ter funcionado) passa a receber
   403. Não deve afetar ninguém usando o fluxo normal via feed — vale
   o Bruno saber que existe essa mudança observável pra quem estivesse
   usando a brecha.
2. **S.1 precisa de teste adversarial** — mesma exigência repetida em
   todas as rodadas anteriores: moderador da Arena A tentando agir
   sobre usuário que só jogou na Arena B → 403; usuário com entry na
   própria Arena → 200.
3. **S.2 é estritamente mais restritivo, sem risco de regressão** —
   antes um não-super via pendentes de todo mundo; agora não vê
   nenhum. Nenhum fluxo hoje depende de um não-super ver o próprio
   pendente na aba Games (a badge só informa status, não há ação
   disponível pra não-super ali).

---

## 6. Implementação (concluída)

- [x] **S.1** — `entry_repo.usuario_tem_entry_na_arena` (nova função) +
  `_exigir_acesso_ao_usuario` em `admin.py`, chamada em
  `GET /usuarios/{user_id}/nicks` e `POST /usuarios/{user_id}/trocar-nick`.
  Super continua irrestrito.
- [x] **S.2** — `GET /games-todos` filtra `pendente_aprovacao` fora da
  resposta quando `not admin.super`.
- [x] Testes: 5 novos (escopo de `historico_nicks`/`trocar-nick` por
  arena — usuário sem entry na arena bloqueado, com entry funciona;
  `games-todos` esconde pendente pra não-super, super continua vendo)
  — suíte completa 673 passed (18 erros de smoke pré-existentes,
  mesmo baseline das rodadas anteriores, confirmado inalterado).
