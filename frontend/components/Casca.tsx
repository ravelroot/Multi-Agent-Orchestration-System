"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ROTULO_STATUS, STATUS_ATIVOS } from "@/lib/eventos";
import type { ResumoExecucao, Saude } from "@/lib/tipos";
import { Icone } from "./Icone";
import { Logo } from "./Logo";

export const EVENTO_HISTORICO = "apogeu:historico";

export function avisarHistorico() {
  window.dispatchEvent(new Event(EVENTO_HISTORICO));
}

const NOME_PROVEDOR: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  ollama: "Ollama",
  demonstracao: "Modo demonstração",
};

function quando(iso: string) {
  const data = new Date(iso);
  const hoje = new Date();
  const mesmoDia = data.toDateString() === hoje.toDateString();
  return mesmoDia
    ? `Hoje, ${data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`
    : data.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

function Historico({ fechar }: { fechar: () => void }) {
  const [itens, setItens] = useState<ResumoExecucao[] | null>(null);
  const parametros = useSearchParams();
  const atual = parametros.get("id");

  const carregar = useCallback(() => {
    api.execucoes().then(setItens).catch(() => setItens([]));
  }, []);

  useEffect(() => {
    carregar();
    window.addEventListener(EVENTO_HISTORICO, carregar);
    return () => window.removeEventListener(EVENTO_HISTORICO, carregar);
  }, [carregar]);

  useEffect(() => {
    if (!itens?.some((i) => STATUS_ATIVOS.includes(i.status))) return;
    const id = setInterval(carregar, 4000);
    return () => clearInterval(id);
  }, [itens, carregar]);

  return (
    <nav className="historico" aria-label="Tarefas anteriores">
      <h2>Tarefas</h2>
      {itens === null && <span className="vazio">Carregando...</span>}
      {itens?.length === 0 && <span className="vazio">As tarefas que você criar aparecem aqui.</span>}
      {itens?.map((i) => (
        <Link key={i.id} href={`/?id=${i.id}`} aria-current={i.id === atual} onClick={fechar} title={`${i.titulo} (${ROTULO_STATUS[i.status]})`}>
          <span className="ponto" data-status={i.status} aria-label={ROTULO_STATUS[i.status]} />
          <span className="titulo">{i.titulo}</span>
          <time dateTime={i.criada_em}>{quando(i.criada_em)}</time>
        </Link>
      ))}
    </nav>
  );
}

function SeletorTema() {
  const [tema, setTema] = useState<"system" | "light" | "dark">("system");
  useEffect(() => {
    try {
      const salvo = localStorage.getItem("apogeu.tema");
      if (salvo === "light" || salvo === "dark") setTema(salvo);
    } catch {}
  }, []);
  const escolher = (valor: "system" | "light" | "dark") => {
    setTema(valor);
    if (valor === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = valor;
    try {
      if (valor === "system") localStorage.removeItem("apogeu.tema");
      else localStorage.setItem("apogeu.tema", valor);
    } catch {}
  };
  return (
    <div className="tema" role="group" aria-label="Tema">
      {(["light", "system", "dark"] as const).map((t) => (
        <button key={t} type="button" aria-pressed={tema === t} onClick={() => escolher(t)}>
          {t === "light" ? "Claro" : t === "dark" ? "Escuro" : "Sistema"}
        </button>
      ))}
    </div>
  );
}

export function Casca({ children }: { children: React.ReactNode }) {
  const [aberta, setAberta] = useState(false);
  const [saude, setSaude] = useState<Saude | null>(null);
  const caminho = usePathname();
  const fechar = () => setAberta(false);

  useEffect(() => {
    api.saude().then(setSaude).catch(() => setSaude(null));
  }, []);

  return (
    <div className="app">
      <aside className="lateral" data-aberta={aberta}>
        <Link href="/" className="marca" onClick={fechar}>
          <Logo />
          <span>Apogeu</span>
        </Link>
        <Link href="/" className="botao primario" onClick={fechar}>
          <Icone nome="mais" />
          Nova tarefa
        </Link>
        <div className="nav">
          <Link href="/equipe/" aria-current={caminho?.startsWith("/equipe") ? "page" : undefined} onClick={fechar}>
            <Icone nome="equipe" />
            Equipe e prompts
          </Link>
        </div>
        <Suspense fallback={null}>
          <Historico fechar={fechar} />
        </Suspense>
        <div className="rodape-lateral">
          <div className="provedor">
            {saude ? (
              <>
                <strong>{NOME_PROVEDOR[saude.provedor.nome] ?? saude.provedor.nome}</strong>
                {saude.provedor.nome === "demonstracao" ? "Respostas de exemplo, sem chave de API" : saude.provedor.modelo}
              </>
            ) : (
              <>
                <strong>API fora do ar</strong>
                Rode iniciar.cmd ou python -m apogeu
              </>
            )}
          </div>
          <SeletorTema />
        </div>
      </aside>
      <div className="principal">
        <header className="topo-movel">
          <Link href="/" className="marca">
            <Logo />
            <span>Apogeu</span>
          </Link>
          <button type="button" className="botao sutil" onClick={() => setAberta(!aberta)} aria-label={aberta ? "Fechar menu" : "Abrir menu"}>
            <Icone nome={aberta ? "fechar" : "menu"} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}
