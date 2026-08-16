# Autenticação e Identidade — Canal3 (Auth Service)

> Status: **decisões fechadas, pronto para commit**. Adaptado a partir de
> um template genérico de plataforma de identidade, cortado e ajustado à escala
> real do Canal3 (eventos presenciais, múltiplos apps futuros).
>
> Complementa `docs/SPEC.md` do `retro-score-ranking` — este documento cobre a
> camada de identidade compartilhada; o `SPEC.md` continua sendo a fonte da
> verdade para o app de ranking em si.

---

## 1. Objetivo e problema motivador

Hoje, no `retro-score-ranking`, o `nick` é texto livre por envio — qualquer
pessoa pode enviar um score usando o nick de outra pessoa, sobrescrevendo a
entrada anterior dela (comportamento de `services/nick.py:
marcar_anterior_como_superado`, incondicional por `nick_norm`). Isso também
impede contagem confiável de participantes únicos e qualquer histórico
consistente por pessoa.

**Além do ranking**, o Canal3 vai lançar outros sistemas (quiz, bonificação,
e outros ainda não definidos) que também vão precisar saber "quem é essa
pessoa" — por isso este não é mais um problema só do `retro-score-ranking`,
e sim de uma identidade compartilhada entre apps Canal3.

### Princípio arquitetural

> O Auth Service é dono da identidade da pessoa. Google, Magic Link e
> futuros provedores são só formas de provar essa identidade. Cada app
> Canal3 (ranking, quiz, bonificação...) é um **consumidor** dessa identidade,
> não o dono dela.

---

## 2. Decisões já fechadas

| # | Tópico | Decisão |
|---|---|---|
| 1 | Formato do `User.id` | UUIDv4 |
| 2 | Account Linking | Automático por e-mail, **somente se `email_verified=true`** no provedor |
| 3 | Escopo | Plataforma compartilhada Canal3 (não só o `retro-score-ranking`) |
| 4 | Modelo de sessão | Híbrido: cookie de sessão no domínio do Auth Service + JWT curto emitido por app consumidor |
| 5 | Provedores no MVP | Google (OIDC) + Magic Link (e-mail) |
| 6 | Login obrigatório? | **Não** — entrada anônima continua funcionando no ranking; login é opt-in |
| 7 | Relação nick ↔ User | Modelo de **claim**: nick fica livre até alguém logar e usar; a partir daí fica reivindicado e protegido para aquela conta |
| 8 | Topologia de domínio dos futuros apps | Ainda não definida — por isso o modelo de sessão (#4) foi escolhido para funcionar em qualquer cenário |
| 9 | Escopo do nick reivindicado | **Plataforma Canal3 inteira** — uma vez reivindicado (em qualquer app), fica reservado em todos os apps consumidores, não só no `retro-score-ranking` |
| 10 | Provedor de e-mail (Magic Link) | Resend (plano gratuito cobre o volume esperado; sem serviço de e-mail hoje no projeto) |
| 11 | TTL de sessão | 30 dias, renovação por uso (sliding) |
| 12 | Retenção do log de auditoria | 1 ano — ver justificativa e nota de LGPD no §5 |
| 13 | CPF/telefone no perfil | **Fora do MVP** — só entra quando o sistema de bonificação for desenhado (evita campo sem uso e reduz dado pessoal coletado sem finalidade imediata, alinhado ao princípio de minimização da LGPD) |

**Fora do MVP, por escolha deliberada** (avaliar depois, não é omissão):
servidor OIDC/OAuth completo com JWKS público e client registry dinâmico,
multi-tenant, barramento de eventos, RBAC/ABAC, Passkey, Apple/Facebook/
Microsoft, SMS/OTP, MFA, SLA formal, multi-region. Ver §9.

---

## 3. Modelo de dados

### `users` (nova tabela — vive no Auth Service)

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | gerado com `gen_random_uuid()`, é o `User.id` canônico |
| `email` | text | não é PK; pode ser nulo só transitoriamente (nunca em produção, já que Google e Magic Link sempre trazem e-mail) |
| `email_verified` | boolean | vem do provedor; condição para account linking automático (#2) |
| `nome` | text nullable | nome vindo do provedor (Google) ou preenchido depois |
| `foto_url` | text nullable | **avatar do perfil** (do provedor, ex. Google) — conceito totalmente separado da foto de evidência de cada score. Cada entrada em `entradas` mantém sua própria `foto_url` (a foto daquele placar específico), imutável, independente do avatar do perfil. |
| `status` | text | `ativo` / `suspenso` — suficiente pro MVP, sem estado mais granular |
| `criado_em` | timestamptz | |
| `ultimo_login_em` | timestamptz | |

### `identities` (nova tabela)

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → users | dono da identidade |
| `provider` | text | `google` \| `magic_link` (mais no futuro) |
| `provider_user_id` | text | `sub` do Google, ou o próprio e-mail normalizado no caso de magic link |
| `email` | text | e-mail trazido por *este* provedor especificamente (pode diferir do `users.email` principal em teoria) |
| `criado_em` | timestamptz | |

`UNIQUE (provider, provider_user_id)` — mesma identidade de provedor nunca se
liga a duas contas.

### `nick_claims` (nova tabela — o coração da correção do bug original)

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `nick_norm` | text | mesma normalização já usada em `entradas.nick_norm` (lowercase + trim + colapso de espaços) |
| `user_id` | uuid FK → users | quem reivindicou |
| `criado_em` | timestamptz | primeiro login com esse nick |

`UNIQUE (nick_norm)` — um nick só pode ser reivindicado por uma conta.

**Escopo: plataforma inteira.** Esta tabela vive no Auth Service, não em
cada app — um nick reivindicado no `retro-score-ranking` fica reservado
automaticamente também para quiz/bonificação/outros apps futuros que
venham a usar nick como identificador público. Não existe uma tabela de
claim por app.

**Regra de claim:** na primeira vez que um `user_id` autenticado envia um
score com um `nick`, se aquele `nick_norm` ainda não está em `nick_claims`,
ele é reivindicado automaticamente para esse `user_id`. Se já está
reivindicado por *outro* `user_id`, o envio é rejeitado com uma mensagem
clara ("Esse nick já tem dono — faça login com a conta certa, ou escolha
outro nick"). Se está reivindicado pelo *mesmo* `user_id`, segue normal.

Envios **anônimos** (sem login) não verificam `nick_claims` para nicks ainda
não reivindicados (comportamento atual, inalterado) — mas **são bloqueados**
se tentarem usar um `nick_norm` que já foi reivindicado por alguém logado.
Isso é o que resolve o problema original sem quebrar a entrada casual sem
conta.

### `sessions` (nova tabela — sessão no domínio do Auth Service)

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | valor do cookie de sessão (opaco) |
| `user_id` | uuid FK → users | |
| `criado_em` | timestamptz | |
| `expira_em` | timestamptz | TTL proposto: 30 dias, renovado a cada uso (sliding) |
| `revogada_em` | timestamptz nullable | logout / revogação manual |
| `user_agent` / `ip_hash` | text nullable | contexto básico, para auditoria — não gestão de dispositivos no MVP (§9) |

### `magic_link_tokens` (nova tabela — suporte ao login por e-mail)

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `email` | text | |
| `token_hash` | text | hash do token (nunca o token em texto puro, igual se faz com senha) |
| `criado_em` | timestamptz | |
| `expira_em` | timestamptz | TTL proposto: 15 minutos |
| `usado_em` | timestamptz nullable | token é single-use — uma vez usado, não serve mais |

### Mudança na tabela `entradas` (retro-score-ranking)

| Coluna nova | Tipo | Notas |
|---|---|---|
| `user_id` | uuid nullable | preenchido se o envio veio de alguém logado; `NULL` = envio anônimo (comportamento atual) |

Não é retroativo — entradas antigas continuam com `user_id = NULL` e
`nick_claims` começa vazia. Ninguém perde nick que já usava; a proteção só
passa a valer a partir do primeiro login real com aquele nick.

---

## 4. Fluxos

### 4.1 Login com Google (OIDC)
```
Visitante toca "Continuar com Google"
   → redirect pro Google (Authorization Code + PKCE)
   → Google autentica, volta com code
   → Auth Service troca code por ID Token, valida (iss, aud, exp, assinatura)
   → busca/cria Identity(provider=google, provider_user_id=sub)
   → busca/cria User (linking automático se email_verified=true bater com User existente)
   → cria Session, seta cookie
```

### 4.2 Login com Magic Link
```
Visitante digita e-mail
   → Auth Service gera token, salva hash em magic_link_tokens, envia e-mail
   → Visitante clica no link (contém o token em claro, só o hash fica no banco)
   → Auth Service valida: existe, não expirou, não foi usado
   → marca usado_em, busca/cria User (email já é "verificado" pelo próprio ato de clicar no link)
   → cria Session, seta cookie
```

### 4.3 Envio de score autenticado (mudança em `POST /api/upload`)
```
Se houver sessão válida (cookie do Auth Service):
   1. Confere nick_claims para o nick_norm enviado
      - livre → reivindica pro user_id atual
      - já é do user_id atual → segue
      - é de outro user_id → 409, mensagem clara
   2. Segue o fluxo de upload já existente, gravando entradas.user_id
Se não houver sessão:
   1. Confere se o nick_norm já está em nick_claims
      - sim → 409 ("esse nick tem dono, faça login")
      - não → segue exatamente como hoje (anônimo)
```

### 4.4 Emissão de token para apps consumidores (multi-app)
```
App consumidor (ex: quiz.canal3.?) redireciona pro Auth Service
   → pessoa já tem sessão? usa direto : loga (4.1 ou 4.2)
   → Auth Service emite JWT curto (TTL: 15 min), assinado, contendo
     {sub: user_id, email, nome, iat, exp, aud: <app>}
   → redireciona de volta pro app consumidor com o JWT
   → app consumidor valida a assinatura localmente (chave pública do Auth
     Service) e mantém sua própria sessão local a partir daí
```
Isso só precisa existir quando o segundo app (quiz/bonificação) for
construído de fato — no MVP do `retro-score-ranking`, só os fluxos 4.1–4.3
são necessários. Mas o desenho de dados acima (`users`/`identities`
separados de `sessions`) já fica pronto para isso sem retrabalho.

---

## 5. Segurança (mínimos do MVP)

- Cookie de sessão: `HttpOnly`, `Secure`, `SameSite=Lax` (suficiente
  enquanto for single-app; revisar para `None` se precisar funcionar
  embutido/cross-site no futuro multi-app).
- Token de magic link: aleatório criptograficamente seguro, **hash** no
  banco (nunca texto puro), single-use, TTL de 15 min.
- Validação completa do ID Token do Google: assinatura via JWKS do Google,
  `iss`, `aud`, `exp`, `nonce`.
- JWT emitido pro app consumidor: assinado (RS256 ou ES256 — chave
  assimétrica, permite apps validarem sem segredo compartilhado), TTL curto
  (15 min), sem refresh token no MVP (a pessoa só re-passa pelo Auth Service
  quando expirar — aceitável na escala de um evento presencial).
- Nunca logar: token de magic link em texto puro, ID Token completo do
  Google, valor do cookie de sessão.
- Rate limit no endpoint de magic link (por e-mail e por IP) — evita abuso
  de envio de e-mail em massa.
- Sessão: TTL de 30 dias, renovado a cada uso (sliding).
- Log de auditoria leve (login, claim de nick, linking): retenção de
  **1 ano**. Justificativa: eventos Canal3 podem ter meses de intervalo
  entre si, e problemas (nick indevidamente reivindicado, linking
  incorreto) tendem a só ser percebidos pela pessoa afetada num evento
  seguinte. Como o log já usa `ip_hash` (nunca IP em texto puro) e serve a
  uma finalidade legítima de segurança/antifraude, 1 ano é uma retenção
  defensável perante a LGPD — mas precisa constar num texto de privacidade
  do Canal3 (mesmo padrão do texto de consentimento já usado em
  `evento_config.lgpd_texto` no ranking).

---

## 6. O que fica fora do MVP (e por quê)

| Item | Motivo de adiar |
|---|---|
| Servidor OIDC/OAuth completo (JWKS público, `/.well-known`, client registry dinâmico) | Só compensa quando existir de fato mais de um app consumidor externo pedindo isso — construir antes é especular infraestrutura |
| Apple / Facebook / Microsoft / SMS | Baixo ganho de conversão nesse contexto (evento presencial, Brasil) vs. custo de manutenção por provedor |
| Passkey | Melhora fricção só em visitas recorrentes; complexidade de implementação (WebAuthn) não se paga ainda no MVP |
| MFA / step-up auth | Não há operação sensível (dinheiro, dados críticos) no ranking hoje que justifique |
| RBAC/ABAC | Autorização de admin já existe separada (`ADMIN_SECRET`); não precisa se fundir com identidade de visitante agora |
| Gestão de múltiplos dispositivos/sessões (listar, revogar individualmente) | Sessão única por vez é suficiente na escala atual |
| Barramento de eventos (`UserCreated`, etc.) | Sem consumidores reais ainda (CRM, antifraude) — adicionar quando existirem |
| Deploy como serviço separado | Construir como módulo dentro do `retro-score-ranking` (FastAPI já existente) primeiro; extrair pra serviço próprio quando o segundo app consumidor for real. O desenho de dados já é feito para permitir essa extração sem redesenho. |

---

## 7. Onde isso vive tecnicamente (proposta)

Construir dentro do backend do `retro-score-ranking` já existente, como um
módulo separado (não misturado com `routers/upload.py` etc.):

```
backend/
  auth/
    router.py        # /api/auth/google/*, /api/auth/magic-link/*, /api/auth/session
    service.py        # lógica de login, linking, emissão de JWT
    repository.py       # users, identities, sessions, nick_claims, magic_link_tokens
  routers/upload.py   # ganha um Depends(sessao_opcional) e a checagem de nick_claims
```

Justificativa: evita subir um serviço/deploy novo (Railway app extra,
domínio extra) antes de precisar de fato — mas mantém a lógica isolada o
suficiente pra virar um serviço próprio depois, quando o quiz/bonificação
existirem, sem precisar reescrever o modelo de dados.

---

## 8. Migração e compatibilidade

- Nenhuma entrada existente muda de comportamento até alguém logar
  ativamente e usar aquele nick pela primeira vez.
- `entradas.user_id` nasce nullable — sem backfill retroativo (não temos
  como saber com segurança qual conta "deveria" ser dona de um nick
  histórico sem pedir confirmação da pessoa, e isso está fora de escopo do
  MVP).
- Se dois nicks diferentes (por variação de digitação) forem na prática a
  mesma pessoa, isso não é resolvido automaticamente — só entra em jogo daqui
  pra frente, uma vez que ela loga com um nick específico.

---

## 9. Todas as perguntas de fechamento foram respondidas

- Envio de Magic Link: **Resend** (plano gratuito cobre o volume esperado).
- TTL de sessão: **30 dias, sliding**.
- Retenção do log de auditoria: **1 ano** (ver justificativa no §5).
- `foto_url` do perfil vs. foto por score: **conceitos separados** — perfil
  tem seu próprio avatar; cada entrada no ranking mantém sua própria foto de
  evidência, sempre (ver §3).
- Escopo do nick reivindicado: **plataforma Canal3 inteira**, não só o
  `retro-score-ranking` (ver §3 e tabela de decisões).
- CPF/telefone no perfil: **fora do MVP**, entra junto com o desenho do
  sistema de bonificação.

### Ainda em aberto, mas explicitamente adiado (não é omissão)

- [ ] Se/quando o `nome`/`foto_url` do perfil vão aparecer no ranking
      público (hoje só o `nick` é público) — decidir quando a UI de perfil
      for desenhada, não bloqueia o schema ou os fluxos de auth.
- [ ] Campo de moderação (`suspenso_motivo` ou similar) em `users.status` —
      só necessário quando houver um caso real de abuso a moderar; adicionar
      via migração simples quando surgir a necessidade.

---

## 10. Próximos passos

1. Fechar as perguntas abertas do §9 (pequenas, não estruturais).
2. Migração SQL para `users`, `identities`, `nick_claims`, `sessions`,
   `magic_link_tokens`, e `entradas.user_id`.
3. Módulo `backend/auth/` com os fluxos do §4.
4. Testes: login Google (mock do provedor), login magic link, claim de
   nick (livre → reivindicado → bloqueio de terceiro → mesmo dono ok),
   upload anônimo continua funcionando sem regressão.
5. Frontend: tela de login opcional no `index.html` (upload), sem tornar o
   fluxo anônimo mais lento para quem não quer logar.
