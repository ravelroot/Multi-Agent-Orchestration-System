"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { NOME_AGENTE } from "@/lib/eventos";
import type { Plano } from "@/lib/tipos";

export function AprovacaoPlano({ id, plano, aoResponder }: { id: string; plano: Plano; aoResponder: () => void }) {
  const [titulo, setTitulo] = useState(plano.titulo);
  const [perguntas, setPerguntas] = useState<string[]>(plano.perguntas);
  const [comentario, setComentario] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function responder(aprovado: boolean) {
    setEnviando(true);
    setErro(null);
    try {
      await api.responderPlano(id, {
        aprovado,
        plano: aprovado ? { ...plano, titulo: titulo.trim() || plano.titulo, perguntas: perguntas.map((p) => p.trim()).filter(Boolean) } : undefined,
        comentario: comentario.trim(),
      });
      aoResponder();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível enviar a resposta.");
      setEnviando(false);
    }
  }

  return (
    <section className="aprovacao" aria-labelledby="titulo-aprovacao">
      <h2 id="titulo-aprovacao">Confira o plano antes da equipe começar</h2>
      <p>{plano.abordagem}</p>
      <div className="campo">
        <label htmlFor="plano-titulo">Título</label>
        <input id="plano-titulo" value={titulo} maxLength={200} onChange={(e) => setTitulo(e.target.value)} />
      </div>
      <div className="campo">
        <span className="rotulo">Perguntas que a pesquisa vai responder</span>
        <div className="lista-perguntas">
          {perguntas.map((p, i) => (
            <div key={i}>
              <input
                id={`pergunta-${i}`}
                aria-label={`Pergunta ${i + 1}`}
                value={p}
                onChange={(e) => setPerguntas(perguntas.map((q, j) => (j === i ? e.target.value : q)))}
              />
              <button type="button" className="botao sutil" onClick={() => setPerguntas(perguntas.filter((_, j) => j !== i))} aria-label={`Remover pergunta ${i + 1}`}>
                Remover
              </button>
            </div>
          ))}
          {perguntas.length < 6 && (
            <button type="button" className="botao sutil" onClick={() => setPerguntas([...perguntas, ""])}>
              Adicionar pergunta
            </button>
          )}
        </div>
      </div>
      <div className="etapas" aria-label="Etapas">
        {plano.etapas.map((e, i) => (
          <span key={i} title={e.objetivo}>
            {i + 1}. {NOME_AGENTE[e.agente]}
          </span>
        ))}
      </div>
      <div className="campo">
        <label htmlFor="plano-comentario">Orientação para a equipe (opcional)</label>
        <textarea id="plano-comentario" rows={2} maxLength={1000} value={comentario} onChange={(e) => setComentario(e.target.value)} placeholder="Ex.: dê exemplos do Rio de Janeiro e evite jargão" />
      </div>
      {erro && <p className="erro-formulario" role="alert">{erro}</p>}
      <div className="botoes">
        <button type="button" className="botao primario" disabled={enviando} onClick={() => responder(true)}>
          Aprovar plano
        </button>
        <button type="button" className="botao perigo" disabled={enviando} onClick={() => responder(false)}>
          Recusar plano
        </button>
      </div>
    </section>
  );
}
