"use client";

import { useEffect, useRef } from "react";
import type { ItemLinha } from "@/lib/eventos";
import { SeloAgente } from "./SeloAgente";

function duracao(ms?: number) {
  if (ms === undefined) return "";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

export function LinhaDoTempo({ itens, ativa }: { itens: ItemLinha[]; ativa: boolean }) {
  const fim = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const coluna = fim.current?.closest(".coluna");
    if (ativa && coluna && coluna.scrollHeight > coluna.clientHeight + 4) {
      coluna.scrollTo({ top: coluna.scrollHeight, behavior: "smooth" });
    }
  }, [itens.length, ativa]);

  if (!itens.length) {
    return <p className="vazio-doc">A equipe está se preparando.</p>;
  }

  return (
    <>
      <ol className="linha-tempo" aria-label="Linha do tempo da equipe">
        {itens.map((i) => (
          <li key={i.id} data-alerta={i.alerta ? "true" : undefined} data-erro={i.erro ? "true" : undefined}>
            <SeloAgente agente={i.agente} pequeno />
            <div className="corpo">
              <div className="titulo-item">
                <span>{i.titulo}</span>
                <span>{i.pendente ? "executando" : duracao(i.duracao)}</span>
              </div>
              {i.tipo === "ferramenta.chamada" ? (
                <details className="ferramenta">
                  <summary>{i.detalhe || "sem argumentos"}</summary>
                  <pre>{JSON.stringify(i.argumentos ?? {}, null, 2)}</pre>
                  <pre className={i.pendente ? "carregando" : undefined}>{i.pendente ? "Aguardando resultado..." : i.resultado}</pre>
                </details>
              ) : (
                i.detalhe && <p className="detalhe">{i.detalhe}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
      <div ref={fim} />
    </>
  );
}
