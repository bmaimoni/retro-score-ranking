// ============================================================
// RETRO SCORE RANKING — Temas por jogo
// ============================================================
// Como adicionar um novo tema:
// 1. Adicione uma entrada neste objeto com o slug exato do jogo
//    cadastrado no banco (ex: "meu-jogo")
// 2. Preencha as três seções: cores, tipografia e assets
// 3. Faça git push — o Vercel aplica automaticamente
//
// Jogo sem tema definido aqui usa o TEMA_PADRAO automaticamente.
// ============================================================

// ── Tema padrão Canal3 ────────────────────────────────────────
// Usado quando o jogo não tem tema próprio definido abaixo.
export const TEMA_PADRAO = {
  cores: {
    bg:        "#0b1331",
    surface:   "#1e184e",
    primary:   "#5e2b82",
    secondary: "#5fbb50",
    accent:    "#72cddd",
  },
  tipografia: {
    font_display: "'Press Start 2P', monospace",
    font_body:    "'Poppins', 'Segoe UI', sans-serif",
    font_url:     "https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Poppins:wght@400;600;700&display=swap",
  },
  assets: {
    icone:      "🎮",
    bg_image:   "",
    bg_overlay: "0.75",
    scanline:   true,
  },
};

// ── Temas por jogo ────────────────────────────────────────────
const TEMAS = {

  "pac-man": {
    cores: {
      bg:        "#0d0d00",
      surface:   "#1a1a00",
      primary:   "#ffcc00",
      secondary: "#ff9900",
      accent:    "#ffffff",
    },
    tipografia: {
      font_display: "'Press Start 2P', monospace",
      font_body:    "'Poppins', sans-serif",
      font_url:     "https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Poppins:wght@400;600;700&display=swap",
    },
    assets: {
      icone:      "🟡",
      bg_image:   "",
      bg_overlay: "0.80",
      scanline:   true,
    },
  },

  "river-raid": {
    cores: {
      bg:        "#001a33",
      surface:   "#002952",
      primary:   "#ff4400",
      secondary: "#00aaff",
      accent:    "#ff8800",
    },
    tipografia: {
      font_display: "'Press Start 2P', monospace",
      font_body:    "'Poppins', sans-serif",
      font_url:     "https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Poppins:wght@400;600;700&display=swap",
    },
    assets: {
      icone:      "✈️",
      bg_image:   "",
      bg_overlay: "0.75",
      scanline:   true,
    },
  },

  "galaga": {
    cores: {
      bg:        "#00001a",
      surface:   "#000033",
      primary:   "#9933ff",
      secondary: "#00ffcc",
      accent:    "#ff3399",
    },
    tipografia: {
      font_display: "'Press Start 2P', monospace",
      font_body:    "'Poppins', sans-serif",
      font_url:     "https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Poppins:wght@400;600;700&display=swap",
    },
    assets: {
      icone:      "🚀",
      bg_image:   "",
      bg_overlay: "0.80",
      scanline:   true,
    },
  },

  "space-invaders": {
    cores: {
      bg:        "#000000",
      surface:   "#0a0a0a",
      primary:   "#00ff00",
      secondary: "#ffffff",
      accent:    "#00ff00",
    },
    tipografia: {
      font_display: "'Press Start 2P', monospace",
      font_body:    "'Share Tech Mono', monospace",
      font_url:     "https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Share+Tech+Mono&display=swap",
    },
    assets: {
      icone:      "👾",
      bg_image:   "",
      bg_overlay: "0.85",
      scanline:   true,
    },
  },

  "donkey-kong": {
    cores: {
      bg:        "#1a0a00",
      surface:   "#2d1500",
      primary:   "#ff6600",
      secondary: "#ffcc00",
      accent:    "#ff3300",
    },
    tipografia: {
      font_display: "'Press Start 2P', monospace",
      font_body:    "'Poppins', sans-serif",
      font_url:     "https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Poppins:wght@400;600;700&display=swap",
    },
    assets: {
      icone:      "🦍",
      bg_image:   "",
      bg_overlay: "0.75",
      scanline:   true,
    },
  },

};

// ── Função principal ──────────────────────────────────────────
// Retorna o tema do jogo pelo slug.
// Se não encontrar, retorna o tema padrão.
export function getTema(slug) {
  return TEMAS[slug] || TEMA_PADRAO;
}

// ── Aplica tema no DOM ────────────────────────────────────────
// Injeta as variáveis CSS no :root e carrega a fonte se necessária.
export function aplicarTema(slug) {
  const tema = getTema(slug);
  const root = document.documentElement;

  // Cores
  root.style.setProperty('--color-bg',           tema.cores.bg);
  root.style.setProperty('--color-bg-surface',   tema.cores.surface);
  root.style.setProperty('--color-bg-surface2',  ajustarBrilho(tema.cores.surface, 0.6));
  root.style.setProperty('--color-primary',      tema.cores.primary);
  root.style.setProperty('--color-primary-glow', hexParaRgba(tema.cores.primary, 0.28));
  root.style.setProperty('--color-secondary',    tema.cores.secondary);
  root.style.setProperty('--color-secondary-glow', hexParaRgba(tema.cores.secondary, 0.22));
  root.style.setProperty('--color-accent',       tema.cores.accent);
  root.style.setProperty('--color-accent-glow',  hexParaRgba(tema.cores.accent, 0.22));

  // Tipografia
  root.style.setProperty('--font-display', tema.tipografia.font_display);
  root.style.setProperty('--font-body',    tema.tipografia.font_body);

  // Carrega fonte se ainda não estiver no documento
  if (tema.tipografia.font_url) {
    const id = `font-tema-${slug}`;
    if (!document.getElementById(id)) {
      const link = document.createElement('link');
      link.id   = id;
      link.rel  = 'stylesheet';
      link.href = tema.tipografia.font_url;
      document.head.appendChild(link);
    }
  }

  // Imagem de fundo
  if (tema.assets.bg_image) {
    const overlay = parseFloat(tema.assets.bg_overlay) || 0.75;
    document.body.style.backgroundImage =
      `linear-gradient(rgba(0,0,0,${overlay}), rgba(0,0,0,${overlay})),
       url('${tema.assets.bg_image}')`;
    document.body.style.backgroundSize     = 'cover';
    document.body.style.backgroundPosition = 'center';
    document.body.style.backgroundAttachment = 'fixed';
  } else {
    document.body.style.backgroundImage = '';
    document.body.style.backgroundColor = tema.cores.bg;
  }

  // Scanline
  root.style.setProperty(
    '--scanline-opacity',
    tema.assets.scanline ? '0.035' : '0'
  );
}

// ── Helpers de cor ────────────────────────────────────────────
function hexParaRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function ajustarBrilho(hex, fator) {
  const r = Math.min(255, Math.floor(parseInt(hex.slice(1, 3), 16) * fator));
  const g = Math.min(255, Math.floor(parseInt(hex.slice(3, 5), 16) * fator));
  const b = Math.min(255, Math.floor(parseInt(hex.slice(5, 7), 16) * fator));
  return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`;
}
