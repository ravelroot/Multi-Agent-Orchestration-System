"use client";

import { useRouter } from "next/navigation";
import { useEffect, useReducer, useRef, useState } from "react";
import { api } from "@/lib/api";
import { AGENTES, ROTULO_STATUS, STATUS_ATIVOS, aplicar, visaoInicial } from "@/lib/eventos";
import type { Evento, Execucao } from "@/lib/tipos";
import { AprovacaoPlano } from "./AprovacaoPlano";
import { avisarHistorico } from "./Casca";
import { Documento } from "./Documento";
import { Icone } from "./Icone";
import { LinhaDoTempo } from "./LinhaDoTempo";
import { SeloAgente } from "./SeloAgente";

const FINAIS = new Set(["execucao.concluida", "execucao.cancelada", "execucao.erro", "plano.recusado", "plano.aguardando"]);

type Acao = { tipo: "eventos"; eventos: Evento[] } | { tipo: "reiniciar" };

function redutor(visao: ReturnType<typeof visaoInicial>, acao: Acao) {
  if (acao.tipo === "reiniciar") return visaoInicial();
  return acao.eventos.reduce(aplicar, visao);
}

export function PainelExecucao({ id }: { id: string }) {
  const router = useRouter();
  const [execucao, setExecucao] = useState<Execucao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [visao, despachar] = useReducer(redutor, undefined, visaoInicial);
  const [conexao, setConexao] = useState(0);
  const [movel, setMovel] = useState<"linha" | "texto">("linha");
  const [confirmarExclusao, setConfirmarExclusao] = useState(false);
  const ultimoSeq = useRef(0);
  ultimoSeq.current = visao.ultimoSeq;

  useEffect(() => {
    despachar({ tipo: "reiniciar" });
    ultimoSeq.current = 0;
    setExecucao(null);
    setErro(null);
    setConfirmarExclusao(false);
    api.obter(id).then(setExecucao).catch((e) => setErro(e.message));
  }, [id]);

  useEffect(() => {
    let fila: Evento[] = [];
    let quadro = 0;
    const descarregar = () => {
      quadro = 0;
      if (fila.length) {
        despachar({ tipo: "eventos", eventos: fila });
        fila = [];
      }
    };
    const fonte = new EventSource(api.urlEventos(id, ultimoSeq.current));
    fonte.onmessage = (mensagem) => {
      const evento: Evento = JSON.parse(mensagem.data);
      fila.push(evento);
      if (!quadro) quadro = requestAnimationFrame(descarregar);
      if (FINAIS.has(evento.tipo)) {
        fonte.close();
        descarregar();
        api.obter(id).then(setExecucao).catch(() => {});
        avisarHistorico();
      }
    };
    fonte.onerror = () => {
      if (fonte.readyState === EventSource.CLOSED) setErro("A conexão com a API caiu. Recarregue a página.");
    };
    return () => {
      fonte.close();
      if (quadro) cancelAnimationFrame(quadro);
    };
  }, [id, conexao]);

  useEffect(() => {
    if (visao.escrevendo) setMovel("texto");
  }, [visao.escrevendo]);

  if (erro && !execucao) {
    return (
      <div className="vazio-doc">
        <strong>{erro}</strong>
        <button className="botao" type="button" onClick={() => router.push("/")}>
          Criar uma nova tarefa
        </button>
      </div>
    );
  }
  if (!execucao) return <div className="carregando-tela">Carregando a tarefa...</div>;

  const status = visao.status ?? execucao.status;
  const ativa = STATUS_ATIVOS.includes(status);

  async function cancelar() {
    try {
      await api.cancelar(id);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível cancelar.");
    }
  }

  async function excluir() {
    await api.excluir(id).catch(() => {});
    avisarHistorico();
    router.push("/");
  }

  return (
    <section className="execucao">
      <header className="cabecalho">
        <div>
          <h1>{visao.plano?.titulo || execucao.titulo}</h1>
          <div className="meta">
            <span className="selo">
              <span className="ponto" data-status={status} />
              {ROTULO_STATUS[status]}
            </span>
            <span>{execucao.briefing.palavras} palavras para {execucao.briefing.publico}</span>
            <span>Tom {execucao.briefing.tom}</span>
            {visao.compactacoes > 0 && <span>Contexto compactado {visao.compactacoes}x</span>}
            {visao.erro && <span>{visao.erro}</span>}
          </div>
        </div>
        <div className="botoes">
          {ativa ? (
            <button type="button" className="botao perigo" onClick={cancelar}>
              <Icone nome="parar" />
              Cancelar tarefa
            </button>
          ) : confirmarExclusao ? (
            <>
              <button type="button" className="botao perigo" onClick={excluir}>
                Excluir de vez
              </button>
              <button type="button" className="botao sutil" onClick={() => setConfirmarExclusao(false)}>
                Manter
              </button>
            </>
          ) : (
            <button type="button" className="botao sutil" onClick={() => setConfirmarExclusao(true)}>
              <Icone nome="lixeira" />
              Excluir
            </button>
          )}
        </div>
      </header>

      <div className="equipe" aria-label="Equipe">
        {AGENTES.map((a) => {
          const estado = visao.agentes[a.chave];
          const uso = estado.limite ? Math.min(100, Math.round((estado.tokens / estado.limite) * 100)) : 0;
          return (
            <div className="membro" key={a.chave} data-estado={estado.estado}>
              <SeloAgente agente={a.chave} />
              <div className="nome">
                {a.nome}
                <small>{estado.estado === "trabalhando" ? "trabalhando" : estado.estado === "concluido" ? "pronto" : "parado"}</small>
              </div>
              <div className="atividade" title={estado.atividade}>
                {estado.atividade}
              </div>
              <div className="medidor" data-alto={uso > 85} title={`Contexto da última chamada: ${estado.tokens} de ${estado.limite} tokens`}>
                <span style={{ width: `${uso}%` }} />
              </div>
            </div>
          );
        })}
      </div>

      <div className="abas-moveis" role="tablist">
        <button type="button" role="tab" aria-selected={movel === "linha"} onClick={() => setMovel("linha")}>
          Linha do tempo
        </button>
        <button type="button" role="tab" aria-selected={movel === "texto"} onClick={() => setMovel("texto")}>
          Texto
        </button>
      </div>

      <div className="paineis" data-movel={movel}>
        <div className="coluna">
          {status === "aguardando_aprovacao" && visao.plano && (
            <div style={{ padding: "18px 20px 0" }}>
              <AprovacaoPlano key={visao.ultimoSeq} id={id} plano={visao.plano} aoResponder={() => setConexao((c) => c + 1)} />
            </div>
          )}
          <LinhaDoTempo itens={visao.linha} ativa={ativa && status !== "aguardando_aprovacao"} />
        </div>
        <div className="coluna">
          <Documento id={id} visao={visao} />
        </div>
      </div>
    </section>
  );
}
