"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Briefing, TipoTexto } from "@/lib/tipos";
import { avisarHistorico } from "./Casca";

const EXEMPLOS = [
  "Escreva um artigo sobre como a energia solar residencial evoluiu no Brasil e quanto custa instalar hoje",
  "Crie um post de blog explicando o que são agentes de IA para pequenas empresas",
  "Produza um relatório técnico comparando PostgreSQL e MongoDB para um sistema de pedidos",
  "Faça um resumo executivo sobre a LGPD para uma escola de idiomas",
];

const TIPOS: { valor: TipoTexto; rotulo: string }[] = [
  { valor: "artigo", rotulo: "Artigo" },
  { valor: "post", rotulo: "Post" },
  { valor: "relatorio", rotulo: "Relatório" },
  { valor: "resumo", rotulo: "Resumo" },
];

export function Compositor() {
  const router = useRouter();
  const [tarefa, setTarefa] = useState("");
  const [briefing, setBriefing] = useState<Briefing>({
    tipo: "artigo",
    publico: "público geral",
    tom: "claro e acessível",
    palavras: 700,
    idioma: "português do Brasil",
  });
  const [aprovarPlano, setAprovarPlano] = useState(false);
  const [maxRevisoes, setMaxRevisoes] = useState(2);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const mudar = <K extends keyof Briefing>(campo: K, valor: Briefing[K]) => setBriefing((b) => ({ ...b, [campo]: valor }));
  const valida = tarefa.trim().length >= 10;

  async function iniciar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!valida || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const execucao = await api.criar({ tarefa: tarefa.trim(), briefing, aprovar_plano: aprovarPlano, max_revisoes: maxRevisoes });
      avisarHistorico();
      router.push(`/?id=${execucao.id}`);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível criar a tarefa.");
      setEnviando(false);
    }
  }

  return (
    <form className="compositor" onSubmit={iniciar}>
      <h1>O que a equipe deve escrever hoje?</h1>
      <p>Descreva o texto. O supervisor monta o plano, o pesquisador busca as fontes, o redator escreve e o revisor só libera quando estiver bom.</p>

      <div className="caixa-tarefa">
        <textarea
          id="tarefa"
          aria-label="Descrição da tarefa"
          placeholder="Ex.: Escreva um artigo sobre os impactos da inteligência artificial no ensino de idiomas, com dados recentes"
          value={tarefa}
          maxLength={2000}
          onChange={(e) => setTarefa(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) iniciar(e);
          }}
        />
        <div className="acoes">
          <span className="contador">{tarefa.length} de 2000 caracteres. Ctrl + Enter inicia.</span>
          <button className="botao primario grande" type="submit" disabled={!valida || enviando}>
            {enviando ? "Reunindo a equipe..." : "Iniciar tarefa"}
          </button>
        </div>
      </div>

      <div className="exemplos" aria-label="Exemplos">
        {EXEMPLOS.map((e) => (
          <button key={e} type="button" onClick={() => setTarefa(e)}>
            {e}
          </button>
        ))}
      </div>

      <div className="opcoes">
        <div className="campo">
          <span className="rotulo" id="rotulo-tipo">Tipo de texto</span>
          <div className="segmentado" role="group" aria-labelledby="rotulo-tipo">
            {TIPOS.map((t) => (
              <button key={t.valor} type="button" aria-pressed={briefing.tipo === t.valor} onClick={() => mudar("tipo", t.valor)}>
                {t.rotulo}
              </button>
            ))}
          </div>
        </div>
        <div className="campo">
          <label htmlFor="palavras">Tamanho</label>
          <select id="palavras" value={briefing.palavras} onChange={(e) => mudar("palavras", Number(e.target.value))}>
            {[300, 500, 700, 1000, 1500, 2000].map((n) => (
              <option key={n} value={n}>
                cerca de {n} palavras
              </option>
            ))}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="publico">Público</label>
          <input id="publico" value={briefing.publico} maxLength={120} onChange={(e) => mudar("publico", e.target.value)} />
        </div>
        <div className="campo">
          <label htmlFor="tom">Tom</label>
          <input id="tom" value={briefing.tom} maxLength={80} onChange={(e) => mudar("tom", e.target.value)} />
        </div>
        <div className="campo">
          <label htmlFor="idioma">Idioma</label>
          <select id="idioma" value={briefing.idioma} onChange={(e) => mudar("idioma", e.target.value)}>
            {["português do Brasil", "inglês", "espanhol", "francês"].map((i) => (
              <option key={i}>{i}</option>
            ))}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="revisoes">Rodadas de revisão</label>
          <select id="revisoes" value={maxRevisoes} onChange={(e) => setMaxRevisoes(Number(e.target.value))}>
            {[0, 1, 2, 3].map((n) => (
              <option key={n} value={n}>
                {n === 0 ? "Só uma revisão, sem reescrever" : `Até ${n} reescrita${n > 1 ? "s" : ""}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      <label className="interruptor" htmlFor="aprovar">
        <input id="aprovar" type="checkbox" checked={aprovarPlano} onChange={(e) => setAprovarPlano(e.target.checked)} />
        <span>
          Quero aprovar o plano antes da equipe começar
          <small>O supervisor para depois de planejar. Você pode editar o título e as perguntas ou deixar uma orientação.</small>
        </span>
      </label>

      {erro && <p className="erro-formulario" role="alert">{erro}</p>}
    </form>
  );
}
