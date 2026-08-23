# Seguir Jogadores: Feed de Atividade por Superação de Score

> Status: **decisões fechadas, pronto para virar código**. Complementa o
> item 1.7 de `docs/BACKLOG_2026.md`. Escrito a partir de uma sessão de
> crítica adversarial — escopo deliberadamente contido: infraestrutura de
> notificação fica de fora, registrada como item de backlog próprio.

---

## 1. Objetivo

Permitir que um jogador siga outro, e receber um sinal simples e
pessoalmente relevante — "fulano te superou num jogo que vocês dois jogam"
— sem construir infraestrutura de notificação (fora de escopo, deliberado)
nem um feed genérico de "tudo que todo mundo fez".

---

## 2. Decisões fechadas

| # | Tópico | Decisão |
|---|---|---|
| 1 | Gatilho da mensagem | Ciclano (seguido) supera fulano (seguidor) **no mesmo jogo**, comparando o **melhor score válido de cada um** (`no_ranking=true`, não superado, não arquivado) — não qualquer envio novo |
| 2 | Escopo da comparação | Melhor score **de todos os tempos** do `user_id`, entre **todos os nicks que ele já usou** — não só o nick atual (consistente com `NICKNAME_SPEC.md`: nick pode trocar, a pessoa por trás não) |
| 3 | Sem backfill | O gatilho não roda retroativamente quando uma relação de seguir começa — só passa a valer daqui pra frente. Seguir alguém com histórico grande não "explode" o feed com superações antigas |
| 4 | Sem notificação em tempo real | Nenhuma infraestrutura de push/e-mail/SSE dedicada a isso agora — **fica registrado como item de backlog próprio**, a avaliar depois |
| 5 | Entrega da informação | Compilada **no momento do login** — não a cada envio de score. Se ciclano bateu o próprio recorde 30 vezes entre dois logins de fulano, fulano vê só o **último** placar de ciclano naquele jogo, não as 30 atualizações |
| 6 | Controle de repetição | Usa `users.ultimo_login_em` (já existe, `AUTH_SPEC.md`) como corte — só superações registradas depois do último login anterior de fulano entram na compilação. Zero tabela nova pra esse mecanismo |
| 7 | Visibilidade cross-marca | Confirmada como aceitável — é dado de ranking já público, categoria diferente do dado administrativo/analytics que `PERMISSOES_SPEC.md` restringe a `super` |
| 8 | Vínculo de "seguir" | Entre `user_id`s — não depende de marca/evento, mesma conta em toda a plataforma |

---

## 3. Por que nenhuma tabela de "eventos de atividade" é necessária

A tentação natural seria criar uma tabela tipo `atividades` (uma linha por
superação detectada). Rejeitado: com entrega compilada no login (decisão
#5) e sem notificação em tempo real (decisão #4), o sinal é **inteiramente
derivável ao vivo**, comparando `entradas` de quem o usuário segue contra
as próprias, filtrando por `criado_em > ultimo_login_em` anterior. Criar
uma tabela espelhada geraria o mesmo risco de sincronização que o projeto
já evita em outros lugares (mesclagem de jogos, claim retroativo de nick)
— mais um lugar pra manter atualizado, sem necessidade real.

---

## 4. Modelo de dados

- `seguidores` (nova): `id`, `seguidor_id` (FK `users`), `seguido_id` (FK
  `users`), `criado_em`. Único por par `(seguidor_id, seguido_id)`.
- Nenhuma coluna nova em `entradas` ou `users` além do que já existe
  (`ultimo_login_em` já cobre o controle de repetição).

---

## 5. Pendência registrada

**Infraestrutura de notificação** (push, e-mail, ou qualquer entrega fora
do momento de login) fica como item de backlog próprio — decisão explícita
de não acoplar essa peça de arquitetura maior a este item.
