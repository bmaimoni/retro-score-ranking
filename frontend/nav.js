// ============================================================
// RETRO SCORE RANKING — Navegação site-wide (hamburguer)
// ============================================================
// docs/BACKLOG_2026.md §3.4: link "Participar" perdido no rodapé →
// navegação real entre as telas. Escopo deliberado: index.html,
// ranking.html e perfil.html chamam inserirNav() com destaque real (têm
// entrada em LINKS abaixo); login.html e play.html também chamam, mas
// sem entrada correspondente — são telas de ação, não destinos de menu
// (ARENA_SPEC.md D.8) — admin.html/console.html ficam com abas próprias
// (modelo autenticado, condicional por nível) e telao.html fica de fora
// (uso passivo, exibição num telão físico, sem navegação por toque).

const LINKS = [
  { id: 'index',   href: 'index.html',   label: 'Início',      icone: '🏠' },
  { id: 'ranking', href: 'ranking.html', label: 'Ranking',     icone: '🏆' },
  { id: 'perfil',  href: 'perfil.html',  label: 'Meu perfil',  icone: '👤' },
];

// paginaAtual: 'index' | 'ranking' | 'perfil' — destaca o link ativo.
// overrides: { [id]: href } — permite a página chamadora preservar
// contexto na navegação (ex: index.html passando 'ranking.html?event=X'
// pra manter o event atual em vez do link genérico).
export function inserirNav(paginaAtual, overrides = {}) {
  if (document.getElementById('site-nav-btn')) return; // evita duplicar

  const style = document.createElement('style');
  style.textContent = `
    .site-nav-btn {
      position: fixed; top: var(--space-md); right: var(--space-md);
      z-index: 1000;
      width: 44px; height: 44px;
      border-radius: var(--radius-md);
      background: rgba(0,0,0,0.4);
      border: 1px solid rgba(255,255,255,0.15);
      color: #fff;
      font-size: 20px;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      backdrop-filter: blur(4px);
      transition: border-color var(--transition);
    }
    .site-nav-btn:hover { border-color: var(--color-primary); }
    .site-nav-backdrop {
      position: fixed; inset: 0; background: rgba(0,0,0,0.6);
      z-index: 999; opacity: 0; pointer-events: none;
      transition: opacity 0.2s ease;
    }
    .site-nav-backdrop.aberto { opacity: 1; pointer-events: auto; }
    .site-nav-painel {
      position: fixed; top: 0; right: -280px; bottom: 0;
      width: 260px; max-width: 80vw;
      background: var(--color-bg-surface, #1e184e);
      border-left: 1px solid rgba(255,255,255,0.1);
      z-index: 1000;
      padding: var(--space-xl) var(--space-lg);
      display: flex; flex-direction: column; gap: var(--space-sm);
      transition: right 0.25s ease;
    }
    .site-nav-painel.aberto { right: 0; }
    .site-nav-link {
      display: flex; align-items: center; gap: 10px;
      padding: 12px 14px;
      border-radius: var(--radius-md);
      color: rgba(255,255,255,0.85);
      text-decoration: none;
      font-size: var(--text-sm);
      transition: background 0.15s;
    }
    .site-nav-link:hover { background: rgba(255,255,255,0.08); }
    .site-nav-link.ativo { color: var(--color-primary, #5e2b82); background: rgba(255,255,255,0.06); }
    .site-nav-fechar {
      align-self: flex-end;
      background: none; border: none; color: rgba(255,255,255,0.6);
      font-size: 24px; line-height: 1; cursor: pointer; margin-bottom: var(--space-md);
      padding: 4px;
    }
    .site-nav-conta {
      display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm);
      padding: 10px 14px;
      margin-bottom: var(--space-sm);
      border-bottom: 1px solid rgba(255,255,255,0.1);
      font-size: var(--text-xs);
      color: rgba(255,255,255,0.75);
      min-height: 1.2em;
    }
    .site-nav-conta-usuario { display: flex; align-items: center; gap: var(--space-sm); overflow: hidden; }
    .site-nav-conta-avatar {
      width: 24px; height: 24px; border-radius: 50%;
      object-fit: cover; flex-shrink: 0;
      border: 1px solid rgba(255,255,255,0.2);
    }
    .site-nav-conta-nome { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .site-nav-conta-sair, .site-nav-conta-entrar {
      background: none; border: none;
      color: var(--color-accent, #72cddd);
      font-size: var(--text-xs);
      cursor: pointer; padding: 0;
      text-decoration: none;
      flex-shrink: 0;
    }
    .site-nav-conta-sair { text-decoration: underline; }
  `;
  document.head.appendChild(style);

  const btn = document.createElement('button');
  btn.id = 'site-nav-btn';
  btn.className = 'site-nav-btn';
  btn.type = 'button';
  btn.setAttribute('aria-label', 'Abrir menu de navegação');
  btn.textContent = '☰';
  document.body.appendChild(btn);

  const backdrop = document.createElement('div');
  backdrop.className = 'site-nav-backdrop';
  document.body.appendChild(backdrop);

  const painel = document.createElement('nav');
  painel.className = 'site-nav-painel';
  painel.setAttribute('aria-label', 'Navegação');
  painel.innerHTML = `
    <button type="button" class="site-nav-fechar" aria-label="Fechar menu">✕</button>
    <div class="site-nav-conta" id="site-nav-conta"></div>
    ${LINKS.map(l => `
      <a href="${overrides[l.id] || l.href}" class="site-nav-link ${l.id === paginaAtual ? 'ativo' : ''}">
        <span aria-hidden="true">${l.icone}</span><span>${l.label}</span>
      </a>
    `).join('')}
  `;
  document.body.appendChild(painel);
  carregarContaNoMenu(painel.querySelector('#site-nav-conta'));

  const abrir  = () => { backdrop.classList.add('aberto'); painel.classList.add('aberto'); };
  const fechar = () => { backdrop.classList.remove('aberto'); painel.classList.remove('aberto'); };

  btn.addEventListener('click', abrir);
  backdrop.addEventListener('click', fechar);
  painel.querySelector('.site-nav-fechar').addEventListener('click', fechar);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fechar(); });
}

// "Logado como" saiu de index.html (pedido do Bruno) e vira info
// site-wide aqui no menu hamburguer, já que ele aparece em toda página
// pública. Checagem própria de sessão — não depende da página chamadora
// já ter feito a sua.
async function carregarContaNoMenu(container) {
  const API_URL = 'https://retro-score-ranking-production.up.railway.app';
  try {
    const resp = await fetch(`${API_URL}/api/auth/session`, { credentials: 'include' });
    if (resp.ok) {
      const usuario = await resp.json();
      const nome = usuario.nome || usuario.email || 'sua conta';
      const avatar = usuario.foto_url
        ? `<img class="site-nav-conta-avatar" src="${escaparHtml(usuario.foto_url)}" alt="">`
        : '';
      container.innerHTML = `
        <span class="site-nav-conta-usuario">${avatar}<span class="site-nav-conta-nome">${escaparHtml(nome)}</span></span>
        <button type="button" class="site-nav-conta-sair" id="site-nav-sair">Sair</button>
      `;
      container.querySelector('#site-nav-sair').addEventListener('click', async () => {
        try { await fetch(`${API_URL}/api/auth/logout`, { method: 'POST', credentials: 'include' }); } catch {}
        location.reload();
      });
      return;
    }
  } catch { /* silencioso — cai no estado deslogado abaixo */ }
  container.innerHTML = `<a href="login.html" class="site-nav-conta-entrar">Entrar</a>`;
}

function escaparHtml(texto) {
  const div = document.createElement('div');
  div.textContent = texto;
  return div.innerHTML;
}
