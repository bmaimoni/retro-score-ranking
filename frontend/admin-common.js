// ============================================================
// RETRO SCORE RANKING — Fundação compartilhada do Painel de Arena
// ============================================================
// docs/PAINEIS_ADMIN_SPEC.md §9 (Fase IV/V) — extraído de admin.html
// pra parar de duplicar login/apiFetch/escapar/showToast/contexto de
// Arena a cada canto novo que vira página própria. Mesmo molde de
// nav.js/temas.js: módulo ES simples, sem build, importado direto via
// <script type="module">.
//
// Mudança de modelo em relação ao admin.html de hoje: lá, TODA página
// tenta logar sozinha (mostra a tela de senha/Google/Magic Link se não
// estiver logada). Aqui, só admin.html continua com a tela de login de
// verdade — as páginas de canto (Jogos, Eventos, Arena, Telão,
// Moderação) só perguntam "tô logado?" via exigirAdmin() e, se não
// estiverem, mandam pra admin.html — que retoma o fluxo de sempre.

export const API_URL = 'https://retro-score-ranking-production.up.railway.app';

let adminSecret = sessionStorage.getItem('admin_secret') || '';
let authMode    = adminSecret ? 'token' : 'session';
let meInfo      = null;

export function getMeInfo() { return meInfo; }
export function getAuthMode() { return authMode; }

export async function apiFetch(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (authMode === 'session') opts.credentials = 'include';
  else opts.headers['Authorization'] = `Bearer ${adminSecret}`;
  if (body) opts.body = JSON.stringify(body);
  return fetch(`${API_URL}${path}`, opts);
}

export function escapar(str = '') {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

export function showToast(msg, tipo = 'success') {
  const t = document.getElementById('toast');
  if (!t) return; // página não tem <div id="toast"> — falha silenciosa, não é crítico
  t.textContent = msg;
  t.className = `toast ${tipo} show`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 3000);
}

export function emptyState(msg) {
  return `<div class="empty-admin">
    <div class="empty-admin-icon">👾</div>
    <div class="empty-admin-text">${msg}</div>
  </div>`;
}

// ── SESSÃO ──────────────────────────────────────────────────────────────────
// Só TENTA restaurar (token salvo, senão cookie) — nunca redireciona
// nem mostra UI. admin.html usa isso puro (cai na tela de login se vier
// null); as páginas de canto usam exigirAdmin() abaixo, que adiciona o
// redirect.
export async function tentarRestaurarSessao() {
  if (adminSecret) {
    try {
      const resp = await fetch(`${API_URL}/api/admin/me`, {
        headers: { Authorization: `Bearer ${adminSecret}` },
      });
      if (resp.ok) {
        meInfo = await resp.json();
        authMode = 'token';
        return meInfo;
      }
    } catch { /* cai pro cookie abaixo */ }
    sessionStorage.removeItem('admin_secret');
    adminSecret = '';
  }

  try {
    const resp = await fetch(`${API_URL}/api/admin/me`, { credentials: 'include' });
    if (resp.ok) {
      meInfo = await resp.json();
      authMode = 'session';
      return meInfo;
    }
  } catch { /* sem sessão nenhuma */ }

  return null;
}

// Uso: páginas de canto (não admin.html). Se não estiver logado, manda
// pra admin.html com ?next= a própria página, pra admin.html poder
// devolver depois (fica pra quando admin.html ganhar essa leitura —
// hoje ainda não redireciona de volta, só evita cair na tela de login
// duas vezes sem explicação).
export async function exigirAdmin() {
  const info = await tentarRestaurarSessao();
  if (info) return info;

  const paginaAtual = location.pathname.split('/').pop() + location.search;
  window.location.href = `admin.html?next=${encodeURIComponent(paginaAtual)}`;
  return null;
}

// ── ARENA ATIVA (docs/PAINEIS_ADMIN_SPEC.md Fase 0/F0.2) ────────────────────
// Antes (admin.html de hoje) a Arena ativa só precisava sobreviver
// dentro da mesma página (troca de aba = mesmo JS, mesma memória).
// Agora que os cantos são páginas separadas, a seleção precisa
// atravessar navegação — por isso sessionStorage aqui, que antes não
// existia pra isso.
let arenaAtual        = null;
let arenasDisponiveis = [];
const listenersArena  = [];

const TIPOGRAFIAS_ADMIN = {
  arcade:    "'Press Start 2P', 'Pixel Operator', monospace",
  futurista: "'Orbitron', sans-serif",
  terminal:  "'Share Tech Mono', monospace",
};

export function getArenaAtual() { return arenaAtual; }
export function getArenasDisponiveis() { return arenasDisponiveis; }

// Chamado toda vez que a Arena ativa muda (inclusive na primeira vez).
// Cada página registra o que precisa recarregar quando isso acontece —
// o módulo não sabe nada sobre Feed/Jogos/Eventos, só avisa.
export function onArenaChange(fn) { listenersArena.push(fn); }

function aplicarBrandingArena(arena) {
  if (!arena) return;
  if (arena.cor_primaria) {
    document.documentElement.style.setProperty('--color-primary', arena.cor_primaria);
  } else {
    document.documentElement.style.removeProperty('--color-primary');
  }
  if (arena.tipografia && TIPOGRAFIAS_ADMIN[arena.tipografia]) {
    document.documentElement.style.setProperty('--font-display', TIPOGRAFIAS_ADMIN[arena.tipografia]);
  } else {
    document.documentElement.style.removeProperty('--font-display');
  }
}

function selecionarArenaAtiva(arenaId, selectorEl) {
  arenaAtual = arenaId;
  sessionStorage.setItem('arena_ativa', arenaId);
  if (selectorEl && selectorEl.value !== arenaId) selectorEl.value = arenaId;
  const arenaObj = arenasDisponiveis.find(a => a.id === arenaId);
  aplicarBrandingArena(arenaObj);
  listenersArena.forEach(fn => fn(arenaId, arenaObj));
}

// selectorEl: <select> opcional — se passado, é populado/escondido
// (1 Arena só = escondido, como já era em admin.html) e ganha o
// onchange. Sem selectorEl, só resolve a Arena ativa e dispara os
// listeners (uso: páginas que herdam a Arena escolhida noutro canto,
// sem oferecer troca própria — nenhuma hoje, mas deixa a porta aberta).
export async function inicializarArenaAtiva(selectorEl = null) {
  try {
    const resp = await apiFetch('/api/admin/arenas');
    if (!resp.ok) return null;
    arenasDisponiveis = await resp.json();
  } catch { return null; }

  if (arenasDisponiveis.length === 0) {
    if (selectorEl) selectorEl.style.display = 'none';
    return null;
  }

  if (selectorEl) {
    if (arenasDisponiveis.length === 1) {
      selectorEl.style.display = 'none';
    } else {
      selectorEl.style.display = 'inline-block';
      selectorEl.innerHTML = arenasDisponiveis.map(a =>
        `<option value="${a.id}">${escapar(a.nome)}</option>`
      ).join('');
      selectorEl.onchange = () => selecionarArenaAtiva(selectorEl.value, selectorEl);
    }
  }

  const salva   = sessionStorage.getItem('arena_ativa');
  const inicial = arenasDisponiveis.some(a => a.id === salva) ? salva : arenasDisponiveis[0].id;
  selecionarArenaAtiva(inicial, selectorEl);
  return arenaAtual;
}

// Events de uma Arena que o admin/moderador atual pode ver — super não
// tem meInfo.events (vê tudo sem escopo), cada página resolve esse caso
// à parte via GET /api/admin/events + filtro por arena_id, se precisar.
export function eventosDaArenaAtiva() {
  if (!meInfo || meInfo.super) return null;
  return (meInfo.events || []).filter(e => e.arena_id === arenaAtual);
}

// ── NÍVEL (docs/PERMISSOES_SPEC.md) ──────────────────────────────────────────
export function ehAdminEmAlgumaArena() {
  if (!meInfo) return false;
  if (meInfo.super) return true;
  return (meInfo.vinculos || []).some(v => v.role === 'admin');
}

export function nivelNaArena(arenaId) {
  if (!meInfo) return null;
  if (meInfo.super) return 'admin';
  const v = (meInfo.vinculos || []).find(v => v.arena_id === arenaId);
  return v ? v.role : null;
}
