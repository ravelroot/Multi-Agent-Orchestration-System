package main

import (
	"html"
	"strings"
)

const scriptJanela = `(() => {
  const externo = (a) => {
    try {
      const u = new URL(a.getAttribute("href"), location.href);
      if (!/^https?:$/.test(u.protocol) || a.hasAttribute("download")) return null;
      return u.origin !== location.origin || a.target === "_blank" ? u.href : null;
    } catch {
      return null;
    }
  };
  const interceptar = (evento) => {
    if (evento.type === "auxclick" && evento.button !== 1) return;
    const a = evento.target instanceof Element ? evento.target.closest("a[href]") : null;
    const destino = a && externo(a);
    if (!destino) return;
    evento.preventDefault();
    evento.stopPropagation();
    window.__apogeuAbrirFora(destino);
  };
  document.addEventListener("click", interceptar, true);
  document.addEventListener("auxclick", interceptar, true);
  const abrirOriginal = window.open;
  window.open = function (endereco, ...resto) {
    try {
      const u = new URL(endereco, location.href);
      if (/^https?:$/.test(u.protocol)) {
        window.__apogeuAbrirFora(u.href);
        return null;
      }
    } catch {}
    return abrirOriginal.call(window, endereco, ...resto);
  };
})();`

const estiloPagina = `:root{--fundo:#e6ddce;--superficie:#f1ebe1;--texto:#2b1d17;--apoio:#5c4034;--borda:#cdbfaa;--borda-forte:#a8977f;--destaque:#5d1c16;--destaque-texto:#faf3e6;--logo:#000;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--fundo:#1d1613;--superficie:#271e1a;--texto:#efe6d8;--apoio:#d6bdb8;--borda:#443530;--borda-forte:#66524a;--destaque:#f6e4a6;--destaque-texto:#2b1d17;--logo:#fff;color-scheme:dark}}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{display:grid;place-items:center;padding:24px;background:var(--fundo);color:var(--texto);font:16px/1.55 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
main{width:min(620px,100%);text-align:center}
svg{display:block;width:96px;height:96px;margin:0 auto;color:var(--logo)}
h1{margin:22px 0 8px;font-size:1.55rem;font-weight:600;letter-spacing:-.01em;text-wrap:balance}
p{max-width:52ch;margin:0 auto;color:var(--apoio);text-wrap:pretty}
.barra{position:relative;width:200px;height:3px;margin:30px auto 0;overflow:hidden;border-radius:3px;background:var(--borda)}
.barra::after{content:"";position:absolute;inset:0;width:40%;border-radius:3px;background:var(--destaque);animation:corre 1.4s ease-in-out infinite}
@keyframes corre{from{transform:translateX(-100%)}to{transform:translateX(250%)}}
@media (prefers-reduced-motion:reduce){.barra::after{width:100%;opacity:.55;animation:none}}
pre{max-height:42vh;margin:24px 0 0;padding:14px 16px;overflow:auto;border:1px solid var(--borda);border-radius:6px;background:var(--superficie);color:var(--texto);font:12.5px/1.5 "Cascadia Mono",Consolas,monospace;text-align:left;white-space:pre-wrap;word-break:break-word}
.acoes{display:flex;flex-wrap:wrap;justify-content:center;gap:10px;margin-top:26px}
.botao{padding:9px 18px;border:1px solid var(--borda-forte);border-radius:6px;background:transparent;color:var(--texto);font:inherit;font-size:.95rem;text-decoration:none;cursor:pointer}
.botao:hover{background:var(--superficie)}
.principal{border-color:var(--destaque);background:var(--destaque);color:var(--destaque-texto)}
.principal:hover{background:var(--destaque);filter:brightness(1.12)}
.botao:focus-visible{outline:2px solid var(--destaque);outline-offset:2px}`

const logoPagina = `<svg viewBox="0 0 64 64" aria-hidden="true"><ellipse cx="32" cy="32" rx="25" ry="10" transform="rotate(-28 32 32)" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="32" cy="32" r="8" fill="currentColor"/><circle cx="9.65" cy="40.01" r="4.5" fill="currentColor"/><circle cx="45.89" cy="17.33" r="4.5" fill="currentColor"/><circle cx="43.96" cy="36.28" r="4.5" fill="currentColor"/></svg>`

func paginaEspera(e etapa) string {
	var b strings.Builder
	b.WriteString(`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Apogeu</title><style>`)
	b.WriteString(estiloPagina)
	b.WriteString(`</style></head><body><main>`)
	b.WriteString(logoPagina)
	b.WriteString(`<h1>` + html.EscapeString(e.titulo) + `</h1>`)
	if e.texto != "" {
		b.WriteString(`<p>` + html.EscapeString(e.texto) + `</p>`)
	}
	if e.carregando {
		b.WriteString(`<div class="barra" role="progressbar" aria-label="Carregando"></div>`)
	}
	if e.detalhe != "" {
		b.WriteString(`<pre>` + html.EscapeString(e.detalhe) + `</pre>`)
	}
	if e.erro {
		b.WriteString(`<div class="acoes"><button class="botao principal" type="button" onclick="window.__apogeuTentarDeNovo()">Tentar de novo</button>`)
		if e.ajuda != "" {
			b.WriteString(`<a class="botao" href="` + html.EscapeString(e.ajuda) + `" target="_blank">` + html.EscapeString(e.ajudaRotulo) + `</a>`)
		}
		if e.registro {
			b.WriteString(`<button class="botao" type="button" onclick="window.__apogeuAbrirRegistro()">Abrir o registro</button>`)
		}
		b.WriteString(`</div>`)
	}
	b.WriteString(`</main></body></html>`)
	return b.String()
}
