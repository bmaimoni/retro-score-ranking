# Permissões: Nível Admin/Moderador, Marca Obrigatória, Titularidade

> Status: **implementado** (migração 019, backend e frontend — ver §7).
> Complementa e
> **revisa** `MARCAS_SPEC.md` §6 (administração escopada) — o modelo de
> autorização daquele documento fica mais rico aqui: ganha uma dimensão de
> nível (admin/moderador), perde a dimensão de evento (marca vira
> obrigatória e o nível cascateia dela pra todos os eventos), e ganha
> titularidade de marca com trava de integridade.
>
> Escrito a partir de uma sessão de crítica adversarial (arquitetura +
> estratégia de produto) — as seções "Riscos identificados" carregam o
> raciocínio de ataque que motivou cada trava, não só a decisão final.

---

## 1. Objetivo

Suportar dois papéis novos dentro de uma marca — **admin** (controle
completo da marca e dos eventos dela) e **moderador** (só modera
pontuações, não cria/edita nada) — preparando o modelo de permissão pra um
cenário que deixou de ser hipotético: **`marca` pode representar um
terceiro pagante**, não só uma sub-divisão interna do Canal3. Isso muda o
padrão de rigor exigido: vazamento cross-marca deixa de ser "bug a
corrigir" e vira "risco existencial pro modelo de negócio B2B".

---

## 2. Decisões fechadas

| # | Tópico | Decisão |
|---|---|---|
| 1 | Contradição original resolvida | Moderador **não** cria jogos — só admin. (A primeira versão do backlog dizia o contrário na seção de Perfil; corrigido.) |
| 2 | Granularidade do nível | **Por vínculo**, não global-por-pessoa — a mesma pessoa pode ser `admin` numa marca e `moderador` (ou nada) noutra |
| 3 | Cascata dentro da marca | Nível definido na marca vale pra **todos os eventos dela** — não existe nível fino por evento dentro de uma marca. Decisão consciente de simplificação (não há demanda real hoje) |
| 4 | `escopo='evento'` em `admin_vinculos` | **Eliminado** — consequência direta da decisão #3 combinada com #6 (evento sempre tem marca). Só restam `super` e `marca` |
| 5 | Quem concede vínculo | `admin` pode conceder `admin` **ou** `moderador`, sempre restrito à própria marca. Só `super` concede/opera fora da própria marca ou concede `super` |
| 6 | Evento sem marca | **Eliminado** — todo evento passa a exigir `marca_id` (mesmo eventos "de edição única") |
| 7 | Quem cria marca | Só `super` — nunca um `admin`, mesmo que "dono" |
| 8 | "Dono" de marca | **Não é super-admin.** É um atributo da marca (`dono_user_id`), aplicado sobre um vínculo `admin` comum. Rejeitado explicitamente o desenho onde dono = super, por vazar acesso cross-marca |
| 9 | Poder extra do dono | Único (além de `super`) que pode revogar vínculo de **outro admin** da mesma marca. Revogar `moderador` continua liberado pra qualquer `admin` |
| 10 | Revogação do dono atual | **Bloqueada** enquanto ele for `dono_user_id` — precisa transferir titularidade primeiro, depois revogar |
| 11 | Transferência de titularidade | Só o dono atual ou `super` iniciam. Só pra alguém que **já tenha** vínculo `admin` ativo na marca (nunca pra um e-mail arbitrário). Dono antigo **mantém** o vínculo `admin` — transferir titularidade ≠ revogar acesso |
| 12 | Auditoria | **Geral**, não só transferência de titularidade — cobre toda concessão/revogação/transferência de vínculo |

---

## 3. Modelo de dados

### `admin_vinculos` (alterada)

```sql
escopo: 'super' | 'marca'   -- 'evento' removido
nivel:  'admin' | 'moderador'  -- NULL quando escopo='super', obrigatório quando escopo='marca'
```
`CHECK` precisa garantir: `escopo='super' → nivel IS NULL` e
`escopo='marca' → nivel IS NOT NULL AND marca_id IS NOT NULL`.

`evento_id` sai da tabela por completo (não existe mais vínculo direto a
evento — tudo passa pela marca).

### `eventos.marca_id` → `NOT NULL`

**Risco de migração identificado**: se existir hoje, em produção, algum
evento sem `marca_id` preenchido, essa alteração falha na hora de rodar.
**Antes de escrever a migração**, preciso consultar o banco real e
confirmar `SELECT COUNT(*) FROM eventos WHERE marca_id IS NULL` = 0. Se
houver órfãos, preciso vinculá-los a uma marca (provavelmente Canal3) antes
do `NOT NULL` entrar.

### `marcas.dono_user_id` (nova coluna)

```sql
dono_user_id uuid REFERENCES users(id)  -- nullable
```
Trava de integridade (aplicada em código, não só em `CHECK` de banco,
porque a regra depende de estado combinado entre duas tabelas): revogar
`admin_vinculos` do usuário que é `dono_user_id` da marca correspondente é
bloqueado — precisa transferir titularidade primeiro.

### `admin_vinculos_auditoria` (nova tabela)

```sql
id           uuid PK
acao         text  -- 'concedido' | 'revogado' | 'titularidade_transferida'
marca_id     uuid FK → marcas
user_alvo_id uuid FK → users        -- quem foi afetado
realizado_por text                  -- identificador de quem fez (mesmo padrão de moderado_por/criado_por)
nivel        text                   -- nível envolvido na ação, quando aplicável
detalhes     jsonb                  -- espaço pra contexto extra sem precisar migrar schema de novo
criado_em    timestamptz
```
Nunca editável, nunca apagável pelo `app_user` (só `INSERT`) — é log, não
estado.

---

## 4. Regras de autorização (tabela final)

| Ação | Moderador | Admin comum | Admin dono | Super |
|---|---|---|---|---|
| Moderar feed | ✅ | ✅ | ✅ | ✅ |
| Criar/editar jogos, eventos, telão (própria marca) | ❌ | ✅ | ✅ | ✅ (qualquer marca) |
| Criar marca nova | ❌ | ❌ | ❌ | ✅ |
| Conceder vínculo admin/moderador (própria marca) | ❌ | ✅ | ✅ | ✅ (qualquer marca) |
| Revogar vínculo de moderador (própria marca) | ❌ | ✅ | ✅ | ✅ |
| Revogar vínculo de **admin** (própria marca) | ❌ | ❌ | ✅ | ✅ |
| Transferir titularidade da marca | ❌ | ❌ | ✅ (só pra admin já vinculado) | ✅ |

---

## 5. Riscos identificados durante o desenho (e a trava correspondente)

Esta seção existe porque o processo de chegar até a tabela acima envolveu
apontar ativamente onde cada versão anterior do desenho quebrava — vale
manter registrado o *porquê*, não só o *o quê*, pra não reabrir esses
buracos numa refatoração futura sem lembrar da razão original.

1. **Escalonamento de privilégio cross-marca.** A versão inicial do
   desenho ("admin concede só nível igual ou menor") tinha duas barreiras
   de segurança independentes. A decisão de permitir admin conceder outro
   admin removeu uma delas — sobrou só a checagem de escopo
   (`marca_id` do vínculo == `marca_id` de quem concede) como única linha
   de defesa contra um admin de uma marca conceder acesso a outra. Essa
   checagem específica **exige teste adversarial explícito** (não só
   caminho feliz) antes de qualquer endpoint de concessão ser considerado
   pronto.

2. **Marca "órfã" de dono.** Se nada impedisse revogar o vínculo do dono
   atual, `marcas.dono_user_id` ficaria apontando pra alguém sem acesso
   nenhum — inconsistência silenciosa, só percebida quando o cliente
   reclamasse de não conseguir mais entrar. Resolvido pela trave de
   integridade (decisão #10).

3. **Dono = super vazando acesso cross-marca.** A primeira proposta de
   "dono de marca = super-admin" foi rejeitada explicitamente — um cliente
   pagante nunca deveria enxergar dados de outro cliente pagante só por
   ser "dono" da própria marca. `super` é cargo da operadora da
   plataforma (Canal3), nunca de um cliente.

4. **Transferência de titularidade pra e-mail arbitrário.** Sem a
   restrição de "só pra quem já é admin vinculado", um dono comprometido
   (conta invadida) poderia doar a marca pra qualquer e-mail de fora.

5. **`POST /api/admin/marcas` sem checagem de `super`** — achado
   incidental durante este desenho: o endpoint hoje aceita **qualquer**
   admin autenticado, não só super. Precisa ser corrigido junto (não é
   consequência de nenhuma decisão nova, é um bug pré-existente que só
   ficou visível ao formalizar "só super cria marca").

---

## 6. Migração e compatibilidade

- **Pré-requisito, antes de escrever a migração de `eventos.marca_id NOT
  NULL`**: confirmar zero eventos órfãos em produção.
- `admin_vinculos` existentes com `escopo='evento'` — nenhum foi criado
  ainda em produção (funcionalidade nova, ainda não usada por ninguém real
  além dos testes) — não há dado a migrar/converter nessa coluna.
- RLS + policy `app_user_all` desde a própria migração pra
  `admin_vinculos_auditoria` (lição já registrada em `SPEC.md` §8 —
  não repetir o bug do telão invisível).
- `marcas.dono_user_id` nasce `NULL` em todas as marcas existentes — a
  marca Canal3 (e qualquer outra já criada) precisa de titularidade
  atribuída manualmente por `super` depois da migração, não é inferido
  automaticamente de nenhum dado existente.

---

## 7. Próximos passos (implementação — concluída)

1. [x] Consultar produção: confirmar zero eventos sem `marca_id` — 0 de 2,
   confirmado antes da migração.
2. [x] Migração `019_permissoes_nivel_marca_obrigatoria.sql`: `admin_vinculos`
   (remove `escopo='evento'`, adiciona `nivel`), `eventos.marca_id NOT NULL`,
   `marcas.dono_user_id`, `admin_vinculos_auditoria` — com RLS/policy desde
   o início. Aplicada em produção.
3. [x] Backend: `middleware/auth.py` (`AdminContext.vinculos` + nível por
   marca) e `repositories/admin_vinculo.py` reescritos; endpoint dedicado de
   transferência de titularidade (`PATCH /api/admin/marcas/{id}/titularidade`);
   `POST /api/admin/marcas` exige `super`; toda concessão/revogação/
   transferência grava em `admin_vinculos_auditoria`. Achados corrigidos no
   caminho (fora da tabela de decisões original, mas mesma régua): escopo
   de marca em `eventos.py` e `teloes_admin.py` (nenhum dos dois checava
   vínculo antes), `limpar/restaurar-ranking` e `atualizar_jogo` sem
   checagem de nível nenhuma.
4. [x] Testes: cobertura adversarial de isolamento cross-marca em cada
   endpoint escopado (vínculos, eventos, jogos, marcas, telões, titularidade).
5. [x] Frontend: `admin.html` corrigido (formulário de vínculos ainda usava
   `escopo='evento'`, quebrado desde a migração) e condicional por nível —
   esconde formulários/botões que o nível atual não permite, em vez de só
   bloquear depois do clique.

**Gaps conhecidos, não bloqueantes:** `GET /api/admin/marcas` e
`GET /api/admin/vinculos` continuam sem escopo por marca (listam tudo pra
qualquer admin autenticado — só a escrita foi travada); resolução de marca
via placar customizado em telões é uma simplificação provisória (ver
`routers/teloes_admin.py`), a revisitar quando `RANKINGS_CONFIGURAVEIS_SPEC.md`
(Fase 4) tratar placar↔marca de verdade.
