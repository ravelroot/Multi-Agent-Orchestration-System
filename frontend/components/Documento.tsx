"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "@/lib/api";
import type { Visao } from "@/lib/eventos";
import { Icone } from "./Icone";
import { Logo } from "./Logo";

type Aba = "texto" | "fontes" | "revisoes" | "notas";

function numero(valor: number | null | undefined, casas = 0) {
  if (valor === null || valor === undefined) return "-";
  return valor.toLocaleString("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: casas });
}

export function Documento({ id, visao }: { id: string; visao: Visao }) {
  const [aba, setAba] = useState<Aba>("texto");
  const [copiado, setCopiado] = useState(false);
  const texto = visao.resultado ?? visao.rascunho;
  const m = visao.metricas;

  async function copiar() {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1800);
    } catch {}
  }

  const abas: { chave: Aba; rotulo: string; total?: number }[] = [
    { chave: "texto", rotulo: "Texto" },
    { chave: "fontes", rotulo: "Fontes", total: visao.fontes.length },
    { chave: "revisoes", rotulo: "Revisões", total: visao.revisoes.length },
    { chave: "notas", rotulo: "Notas da pesquisa" },
  ];

  return (
    <div className="documento">
      <div className="abas" role="tablist">
        {abas.map((a) => (
          <button key={a.chave} role="tab" aria-selected={aba === a.chave} onClick={() => setAba(a.chave)} type="button">
            {a.rotulo}
            {a.total ? <span>{a.total}</span> : null}
          </button>
        ))}
      </div>
      <div className="conteudo-aba" role="tabpanel">
        {aba === "texto" &&
          (texto ? (
            <>
              <div className="barra-doc">
                <span>
                  {visao.resultado ? "Versão final" : visao.escrevendo ? `Escrevendo a versão ${visao.versao}...` : `Rascunho, versão ${visao.versao}`}
                </span>
                <div className="botoes">
                  <button type="button" className="botao sutil" onClick={copiar}>
                    <Icone nome={copiado ? "ok" : "copiar"} />
                    {copiado ? "Copiado" : "Copiar"}
                  </button>
                  {visao.resultado && (
                    <>
                      <button type="button" className="botao sutil" onClick={() => api.baixar(id, "markdown")}>
                        <Icone nome="baixar" />
                        Markdown
                      </button>
                      <button type="button" className="botao sutil" onClick={() => api.baixar(id, "json")}>
                        <Icone nome="baixar" />
                        JSON
                      </button>
                    </>
                  )}
                </div>
              </div>
              {m && (
                <dl className="metricas">
                  <div>
                    <dt>Nota</dt>
                    <dd>{numero(m.nota, 1)}</dd>
                  </div>
                  <div>
                    <dt>Palavras</dt>
                    <dd>{numero(m.palavras)}</dd>
                  </div>
                  <div>
                    <dt>Leitura</dt>
                    <dd>{m.minutos_leitura} min</dd>
                  </div>
                  <div>
                    <dt>Versões</dt>
                    <dd>{numero(m.versoes)}</dd>
                  </div>
                  <div>
                    <dt>Fontes citadas</dt>
                    <dd>
                      {numero(m.fontes_citadas)} de {numero(m.fontes_consultadas)}
                    </dd>
                  </div>
                  <div>
                    <dt>Tokens</dt>
                    <dd>{numero(((m.tokens_entrada ?? 0) + (m.tokens_saida ?? 0)) / 1000, 1)} mil</dd>
                  </div>
                </dl>
              )}
              <article className="texto-final">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer noopener" /> }}>
                  {texto}
                </ReactMarkdown>
                {visao.escrevendo && <span className="cursor-escrita" aria-hidden="true" />}
              </article>
            </>
          ) : (
            <div className="vazio-doc">
              <Logo titulo="" />
              <strong>{visao.status === "aguardando_aprovacao" ? "O texto começa depois que você aprovar o plano" : "O texto aparece aqui enquanto o redator escreve"}</strong>
              <span>Acompanhe a pesquisa e as decisões do supervisor na linha do tempo.</span>
            </div>
          ))}
        {aba === "fontes" &&
          (visao.fontes.length ? (
            <ol className="lista-fontes">
              {visao.fontes.map((f) => (
                <li key={f.id}>
                  <span className="n">[{f.id}]</span>
                  <div>
                    <a href={f.url} target="_blank" rel="noreferrer noopener">
                      {f.titulo}
                    </a>
                    {f.trecho && <p>{f.trecho}</p>}
                    <small>{f.url}</small>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="vazio-doc">As fontes encontradas pelo pesquisador aparecem aqui, numeradas como no texto.</p>
          ))}
        {aba === "revisoes" &&
          (visao.revisoes.length ? (
            <div className="revisoes">
              {visao.revisoes.map((r) => (
                <article className="revisao" key={r.versao}>
                  <header>
                    <div>
                      <strong>Versão {r.versao}</strong>
                      <div className="selo">{r.aprovado ? "Aprovada" : "Pediu correções"}</div>
                    </div>
                    <span className="nota">{numero(r.nota, 1)}</span>
                  </header>
                  {r.pontos_fortes.length > 0 && (
                    <>
                      <h3>Pontos fortes</h3>
                      <ul>{r.pontos_fortes.map((p) => <li key={p}>{p}</li>)}</ul>
                    </>
                  )}
                  {r.problemas.length > 0 && (
                    <>
                      <h3>Problemas</h3>
                      <ul>{r.problemas.map((p) => <li key={p}>{p}</li>)}</ul>
                    </>
                  )}
                  {r.sugestoes.length > 0 && (
                    <>
                      <h3>Sugestões para o redator</h3>
                      <ul>{r.sugestoes.map((p) => <li key={p}>{p}</li>)}</ul>
                    </>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <p className="vazio-doc">Cada revisão traz nota, problemas e sugestões. A primeira chega depois do primeiro rascunho.</p>
          ))}
        {aba === "notas" &&
          (visao.notas ? <pre className="notas-pesquisa">{visao.notas}</pre> : <p className="vazio-doc">As notas do pesquisador aparecem aqui, com as citações [n].</p>)}
      </div>
    </div>
  );
}
